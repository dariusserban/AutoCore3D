"""Creierul: contextul comun si masina de stari care alege ce se face acum.

Modelul e o lista de comportamente cu prioritati. La fiecare ciclu, motorul
intreaba comportamentele in ordine descrescatoare a prioritatii: "tu ai ceva
de facut acum?". Primul care spune da, ruleaza, apoi ciclul reincepe de sus.

Ordinea conteaza: daca ai 20% viata, nu vrei sa mai culegi flori. De aceea
supravietuirea are prioritate 100, iar mersul pe traseu doar 10 - mersul e ce
faci cand nu e nimic mai important de facut.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from . import vision
from .capture import Region
from .config import Profile
from .input_ctl import InputController
from .navigation import RoutePlayer
from .route import Waypoint
from .safety import KillSwitch, SessionGuard, Watchdog

log = logging.getLogger(__name__)

# Etichetele reperelor sunt scrise din perspectiva jucatorului ("aici e un
# vendor"), iar comportamentele din perspectiva actiunii ("aici fac intretinere").
# Tabelul leaga cele doua vocabulare.
ZONE_ALIASES: dict[str, tuple[str, ...]] = {
    "upkeep": ("vendor", "repair"),
    "idle_click": ("idle",),
}


@dataclass
class Stats:
    """Ce s-a intamplat in sesiune. Se afiseaza la final."""

    started_at: float = field(default_factory=time.monotonic)
    kills: int = 0
    gathers: int = 0
    loots: int = 0
    heals: int = 0
    laps: int = 0
    recoveries: int = 0
    upkeep_runs: int = 0

    @property
    def runtime_minutes(self) -> float:
        return (time.monotonic() - self.started_at) / 60.0

    def summary(self) -> str:
        minutes = max(self.runtime_minutes, 0.01)
        return (
            f"Sesiune: {minutes:.1f} min | ture: {self.laps} | ucideri: {self.kills} "
            f"({self.kills/minutes*60:.0f}/h) | culese: {self.gathers} | "
            f"loot: {self.loots} | vindecari: {self.heals} | recuperari: {self.recoveries}"
        )


class BotContext:
    """Tot ce au nevoie comportamentele ca sa decida si sa actioneze."""

    def __init__(
        self,
        profile: Profile,
        capture,
        controller: InputController,
        templates,
        kill_switch: KillSwitch,
        watchdog: Watchdog,
        session: SessionGuard,
        player: Optional[RoutePlayer] = None,
    ) -> None:
        self.profile = profile
        self.capture = capture
        self.controller = controller
        self.templates = templates
        self.kill_switch = kill_switch
        self.watchdog = watchdog
        self.session = session
        self.player = player
        self.stats = Stats()

        self.current_waypoint: Optional[Waypoint] = None
        self.frame: Optional[np.ndarray] = None
        # Cat timp mai stationam la reperul curent ca sa farmam pe loc.
        self.dwell_until: float = 0.0
        # Ridicat de lupta: pozitia pe traseu nu mai e de incredere.
        self.needs_resync: bool = False

    # ---------------------------------------------------------------- cadru

    def refresh(self) -> np.ndarray:
        """Un cadru nou al intregului ecran, alimentand si watchdog-ul."""
        self.frame = self.capture.grab()
        self.watchdog.observe_frame(self.frame)
        return self.frame

    def crop(self, region_name: str) -> Optional[np.ndarray]:
        """Decupeaza o regiune definita in profil din cadrul curent."""
        region = self.profile.region(region_name)
        if region is None or self.frame is None:
            return None
        return self.frame[region.top : region.bottom, region.left : region.right]

    # ------------------------------------------------------------- masurari

    def bar_ratio(self, region_name: str, color_name: str) -> Optional[float]:
        """Cat la suta e plina o bara. None daca profilul nu o defineste."""
        image = self.crop(region_name)
        color = self.profile.color(color_name)
        if image is None or color is None:
            return None
        return vision.bar_fill_ratio(image, color.low, color.high)

    @property
    def health(self) -> Optional[float]:
        return self.bar_ratio("health_bar", "health")

    @property
    def target_health(self) -> Optional[float]:
        return self.bar_ratio("target_health_bar", "health")

    def has_target(self) -> bool:
        """Avem o tinta selectata? Deducem din prezenta barei de viata a tintei."""
        region = self.profile.region("target_health_bar")
        color = self.profile.color("health")
        if region is None or color is None or self.frame is None:
            return False
        crop = self.frame[region.top : region.bottom, region.left : region.right]
        # Bara tintei dispare complet cand nu ai tinta, deci orice urma de
        # culoare peste un prag mic inseamna ca exista ceva selectat.
        return vision.bar_fill_ratio(crop, color.low, color.high) > 0.03

    def find_blobs(self, color_name: str, region_name: Optional[str] = None, min_area: int = 60):
        """Pete de o anumita culoare (nameplate-uri, noduri), in coord. de ecran."""
        color = self.profile.color(color_name)
        if color is None or self.frame is None:
            return []
        region = self.profile.region(region_name) if region_name else None
        image = self.crop(region_name) if region_name else self.frame
        if image is None:
            return []
        blobs = vision.color_blobs(image, color.low, color.high, min_area=min_area)
        if region is None:
            return blobs
        # Coordonatele vin relative la decupaj; le mutam in sistemul ecranului.
        return [
            vision.Match(b.x + region.left, b.y + region.top, b.width, b.height, b.score)
            for b in blobs
        ]

    def screen_center(self) -> tuple[int, int]:
        region: Region = self.capture.monitor
        return region.center

    def running(self) -> bool:
        return self.kill_switch.running()

    # ----------------------------------------------------------------- zone

    def zone_allows(self, activity: str) -> bool:
        """Are voie activitatea asta in zona in care ne aflam acum?

        Reperele de pe ruta poarta o eticheta ('combat', 'gather', ...). Botul
        lupta doar in zonele de lupta si culege doar in cele de resurse, ca sa
        nu se ia dupa primul mob agresiv de langa drum si sa se rupa traseul.
        Cu `anywhere: true` in profil, activitatea devine permisa peste tot.
        """
        if self.profile.section(activity).get("anywhere", False):
            return True
        if self.current_waypoint is None:
            return True  # rulare fara ruta: nimic nu ne restrictioneaza
        permise = ZONE_ALIASES.get(activity, (activity,))
        return self.current_waypoint.kind in permise

    def dwelling(self) -> bool:
        """Stam pe loc la un reper (farmam acolo) in loc sa mergem mai departe?"""
        return time.monotonic() < self.dwell_until


class Behavior:
    """Un comportament: stie sa spuna daca e cazul sa ruleze, si sa ruleze."""

    name = "behavior"
    priority = 0

    def enabled(self, ctx: BotContext) -> bool:
        return ctx.profile.enabled(self.name)

    def should_run(self, ctx: BotContext) -> bool:
        """Se uita la ecran si raspunde: e momentul meu?"""
        raise NotImplementedError

    def run(self, ctx: BotContext) -> None:
        """Executa. Trebuie sa se termine relativ repede si sa verifice
        `ctx.running()` daca dureaza."""
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} prio={self.priority}>"


class BehaviorEngine:
    """Bucla principala. Alege comportamentul cu prioritatea cea mai mare."""

    def __init__(self, ctx: BotContext, behaviors: list[Behavior], tick: float = 0.25) -> None:
        self.ctx = ctx
        self.behaviors = sorted(behaviors, key=lambda b: b.priority, reverse=True)
        self.tick = tick
        self.active: list[Behavior] = [b for b in self.behaviors if b.enabled(ctx)]
        log.info("Comportamente active: %s", ", ".join(b.name for b in self.active) or "niciunul")

    def step(self) -> Optional[Behavior]:
        """Un singur ciclu de decizie. Intoarce comportamentul care a rulat."""
        self.ctx.refresh()
        for behavior in self.active:
            try:
                if behavior.should_run(self.ctx):
                    log.debug("Rulez comportamentul: %s", behavior.name)
                    behavior.run(self.ctx)
                    return behavior
            except Exception:
                # Un comportament care crapa nu trebuie sa opreasca botul cu
                # tastele apasate si personajul alergand in perete.
                log.exception("Comportamentul '%s' a aruncat exceptie.", behavior.name)
                self.ctx.controller.release_all()
        return None

    def run_forever(self) -> str:
        """Ruleaza pana la oprire. Intoarce motivul opririi."""
        ctx = self.ctx
        while True:
            if ctx.kill_switch.stopped:
                return "oprit de la tastatura"
            if ctx.kill_switch.paused:
                time.sleep(0.3)
                continue
            if ctx.session.expired():
                return f"limita de sesiune atinsa ({ctx.session.max_runtime_minutes:.0f} min)"

            reason = ctx.watchdog.should_abort()
            if reason:
                return reason

            if ctx.session.break_due():
                ctx.controller.release_all()
                ctx.session.take_break(interruptible=ctx.running)
                ctx.watchdog.reset_stuck()
                continue

            self.step()
            time.sleep(self.tick)
