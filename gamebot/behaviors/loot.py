"""Adunarea obiectelor cazute pe jos.

In ARPG-uri obiectele cad cu o eticheta colorata deasupra, iar culoarea spune
raritatea. Le gasim dupa culoarea aia si dam click pe ele.

Doua lucruri invatate din felul in care se comporta jocurile:

Nu dam click la nesfarsit pe acelasi obiect. Daca e in spatele unui gard sau
prea departe, clicul nu face nimic, iar botul ar ramane blocat acolo pana la
capatul sesiunii. Tinem minte ce am incercat si trecem mai departe.

Luam intai ce e aproape de personaj. Un obiect din celalalt capat al ecranului
il face pe personaj sa traverseze toata harta si sa iasa din traseu; astea sunt
lasate in seama razei de adunare, care le exclude.
"""

from __future__ import annotations

import logging
import math
import time

from ..core import humanize
from ..core.engine import Behavior, BotContext
from ..core.pickup import Blacklist

log = logging.getLogger(__name__)


class LootBehavior(Behavior):
    name = "loot"
    priority = 65  # dupa lupta, inaintea mersului si a culesului de resurse

    def __init__(self) -> None:
        self._incercate = Blacklist()
        self._ultima_trecere = 0.0

    def enabled(self, ctx: BotContext) -> bool:
        section = ctx.profile.section("loot")
        # Are sens doar daca stim ce culori sa cautam, sau daca exista o tasta
        # de ridicare pe care sa o apasam periodic.
        return ctx.profile.enabled("loot", True) and bool(
            section.get("colors") or ctx.profile.key("loot")
        )

    def should_run(self, ctx: BotContext) -> bool:
        section = ctx.profile.section("loot")
        if time.monotonic() - self._ultima_trecere < float(section.get("interval", 1.0)):
            return False
        if self._obiecte(ctx):
            return True
        # Fara etichete vizibile, mai apasam din cand in cand tasta de ridicare,
        # daca jocul are una - unele ridica tot ce e in jur, fara sa vezi ceva.
        tasta = ctx.profile.key("loot")
        return bool(tasta) and bool(section.get("press_key_blindly", False))

    def run(self, ctx: BotContext) -> None:
        section = ctx.profile.section("loot")
        self._ultima_trecere = time.monotonic()

        tasta = ctx.profile.key("loot")
        if tasta:
            ctx.controller.key(str(tasta))
            humanize.sleep(0.25, 0.3)

        obiecte = self._obiecte(ctx)
        if not obiecte:
            return

        cx, cy = ctx.screen_center()
        obiecte.sort(key=lambda b: math.hypot(b.center[0] - cx, b.center[1] - cy))
        maxim = int(section.get("max_per_pass", 4))

        luate = 0
        for blob in obiecte[:maxim]:
            if not ctx.running():
                return
            x, y = blob.center
            # Eticheta sta deasupra obiectului; clicul trebuie sa cada pe obiect.
            ctx.controller.click(x, y + int(section.get("click_offset_y", 12)))
            self._noteaza(x, y)
            luate += 1
            humanize.sleep(float(section.get("click_delay", 0.45)), 0.3)

        if luate:
            ctx.stats.loots += luate
            log.debug("Am incercat sa ridic %d obiect(e).", luate)

    # ------------------------------------------------------------- ajutator

    def _obiecte(self, ctx: BotContext) -> list:
        """Etichetele de obiect vizibile, minus cele incercate recent."""
        section = ctx.profile.section("loot")
        culori = section.get("colors") or []
        if isinstance(culori, str):
            culori = [culori]

        raza = float(section.get("pickup_radius", 0)) or 0.0
        cx, cy = ctx.screen_center()
        min_area = int(section.get("min_area", 25))

        max_area = int(section.get("max_area", 3000))
        blobs = []
        for nume in culori:
            for b in ctx.find_blobs(nume, min_area=min_area):
                # Un monstru de culoarea potrivita nu e un obiect pe jos.
                if b.width * b.height <= max_area:
                    blobs.append(b)

        self._incercate.seconds = float(section.get("blacklist_seconds", 20.0))

        rezultat = []
        for b in blobs:
            bx, by = b.center
            if raza > 0 and math.hypot(bx - cx, by - cy) > raza:
                continue
            if self._incercate.contains(bx, by):
                continue
            rezultat.append(b)
        return rezultat

    def _noteaza(self, x: int, y: int) -> None:
        self._incercate.add(x, y)
