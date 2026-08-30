"""Lupta: gaseste tinta, apropie-te, roteste skill-urile, ia loot-ul.

Selectia tintei se face in doua feluri, in functie de ce ai in profil:
  - `keys.target_next` (de obicei Tab): cel mai fiabil, jocul alege tinta;
  - nameplate-uri: cautam pete de o anumita culoare deasupra mob-urilor si
    dam click pe cea mai apropiata de centrul ecranului.

Rotatia de skill-uri nu e o secventa fixa apasata la infinit: alegem urmatoarea
tasta din lista, cu mici variatii de ordine, ca sa nu iasa un tipar mecanic
perfect identic la fiecare mob.
"""

from __future__ import annotations

import logging
import math
import time

from ..core import humanize
from ..core.engine import Behavior, BotContext

log = logging.getLogger(__name__)


class CombatBehavior(Behavior):
    name = "combat"
    priority = 70

    def __init__(self) -> None:
        self._rotation_index = 0
        self._last_target_attempt = 0.0
        self._last_used: dict[str, float] = {}

    def should_run(self, ctx: BotContext) -> bool:
        if not ctx.zone_allows("combat"):
            return False
        if ctx.has_target():
            return True
        # Fara tinta: intram doar daca vedem ceva de atacat sau daca avem o
        # tasta de selectie pe care sa o incercam.
        if ctx.profile.key("target_next"):
            return True
        return bool(ctx.find_blobs("enemy_nameplate", min_area=40))

    def run(self, ctx: BotContext) -> None:
        section = ctx.profile.section("combat")

        if not ctx.has_target() and not self._acquire_target(ctx):
            return

        self._approach(ctx, float(section.get("approach_seconds", 0.0)))
        killed = self._fight(ctx, float(section.get("max_fight_seconds", 45.0)))

        # Lupta ne-a mutat: am fugit dupa mob, ne-am rotit, ne-am oprit in alta
        # parte. Traseul trebuie sa isi verifice pozitia inainte sa mearga mai
        # departe, altfel reia secventa inregistrata din directia gresita.
        ctx.needs_resync = True

        if killed:
            ctx.stats.kills += 1
            print(f"  + mob ucis (total {ctx.stats.kills})")
            if section.get("loot_after_kill", True):
                self._loot(ctx)

    # ------------------------------------------------------------ selectie

    def _acquire_target(self, ctx: BotContext) -> bool:
        """Incearca sa selecteze un mob. Intoarce True daca a reusit."""
        now = time.monotonic()
        if now - self._last_target_attempt < 0.6:
            return False
        self._last_target_attempt = now

        target_key = ctx.profile.key("target_next")
        if target_key:
            ctx.controller.key(str(target_key))
            humanize.sleep(0.35, 0.25)
            ctx.refresh()
            if ctx.has_target():
                return True

        # Varianta vizuala: click pe nameplate-ul cel mai apropiat de centru,
        # fiindca ala e cel mai probabil in raza si in fata personajului.
        blobs = ctx.find_blobs("enemy_nameplate", min_area=40)
        if not blobs:
            return False

        cx, cy = ctx.screen_center()
        nearest = min(blobs, key=lambda b: math.hypot(b.center[0] - cx, b.center[1] - cy))
        # Click putin sub nameplate: acolo e corpul mob-ului, nu textul.
        ctx.controller.click(nearest.center[0], nearest.center[1] + nearest.height)
        humanize.sleep(0.4, 0.25)
        ctx.refresh()
        return ctx.has_target()

    def _approach(self, ctx: BotContext, seconds: float) -> None:
        """Mers inainte cateva momente, ca tinta sa intre in raza.

        Fara acces la distanta reala, mergem o durata fixa din profil. Daca
        jocul tau are auto-attack cu apropiere automata, lasa 0.
        """
        if seconds <= 0:
            return
        forward = ctx.profile.key("forward", "w")
        ctx.controller.hold(str(forward), humanize.delay(seconds, 0.2))

    # --------------------------------------------------------------- lupta

    def _next_ability(self, ctx: BotContext) -> Optional[str]:
        """Urmatoarea abilitate de apasat, dupa cooldown-urile invatate.

        Daca profilul are `combat.abilities` (scris de comanda `learn`), mergem
        pe prioritati: prima abilitate din lista care si-a terminat cooldown-ul.
        Lista e ordonata cu cele grele primele, deci lovitura mare pleaca de
        indata ce e gata, iar cele scurte umplu golurile.

        Fara lista invatata, cadem pe `keys.attack_rotation`, apasata pe rand.
        """
        now = time.monotonic()
        abilities = ctx.profile.section("combat").get("abilities") or []

        if abilities:
            for entry in abilities:
                key = str(entry.get("key", ""))
                if not key:
                    continue
                cooldown = float(entry.get("cooldown", 0.0))
                if now - self._last_used.get(key, 0.0) >= cooldown:
                    self._last_used[key] = now
                    return key
            return None  # toate sunt pe cooldown: asteptam o runda

        rotation = [str(k) for k in (ctx.profile.key("attack_rotation") or [])]
        if not rotation:
            return None
        key = rotation[self._rotation_index % len(rotation)]
        self._rotation_index += 1
        return key

    def _fight(self, ctx: BotContext, timeout: float) -> bool:
        """Roteste abilitatile pana moare tinta sau expira timpul.

        Intoarce True daca tinta a disparut (presupunem ca a murit), False daca
        am renuntat - de obicei semn ca mob-ul e prea tare sau ne-a scapat.
        """
        section = ctx.profile.section("combat")
        if not section.get("abilities") and not ctx.profile.key("attack_rotation"):
            log.warning("Nicio abilitate configurata; nu pot lupta. Ruleaza `learn`.")
            return False

        gcd = float(section.get("global_cooldown", 1.4))
        deadline = time.monotonic() + timeout
        saw_target = False

        while time.monotonic() < deadline:
            if not ctx.running():
                return False

            ctx.refresh()
            if ctx.has_target():
                saw_target = True
            elif saw_target:
                return True  # aveam tinta, acum nu mai e: a murit
            else:
                return False  # n-am avut niciodata tinta

            health = ctx.health
            if health is not None and health <= ctx.profile.threshold("heal_below", 0.5):
                # Iesim din lupta si lasam comportamentul de supravietuire, care
                # are prioritate mai mare, sa preia la ciclul urmator.
                return False

            key = self._next_ability(ctx)
            if key:
                ctx.controller.key(key)
            humanize.sleep(gcd, 0.18)

        log.info("Lupta a depasit timpul alocat; renunt la tinta.")
        return False

    # ---------------------------------------------------------------- loot

    def _loot(self, ctx: BotContext) -> None:
        """Ridica ce a cazut. Doua variante: tasta de loot sau click pe sac."""
        section = ctx.profile.section("combat")
        humanize.sleep(float(section.get("loot_delay", 1.2)), 0.2)

        loot_key = ctx.profile.key("loot")
        if loot_key:
            for _ in range(int(section.get("loot_presses", 2))):
                ctx.controller.key(str(loot_key))
                humanize.sleep(0.5, 0.25)
            ctx.stats.loots += 1
            return

        # Fara tasta: cautam sablonul sacului de loot pe ecran.
        if ctx.templates.has("loot_bag"):
            from ..core import vision

            ctx.refresh()
            match = vision.find_template(
                ctx.frame, ctx.templates["loot_bag"], ctx.profile.threshold("template_match", 0.85)
            )
            if match:
                ctx.controller.click(*match.center, double=True)
                ctx.stats.loots += 1
                humanize.sleep(1.0, 0.2)
