"""Culesul de resurse: gaseste nodul, da click, asteapta bara de cules.

Nodurile nu au forma constanta (o tufa arata altfel din fiecare unghi), deci
template matching e fragil aici. Mergem pe culoare: majoritatea jocurilor
scot in evidenta resursele cu un contur sau o sclipire de o nuanta anume.
Daca jocul tau afiseaza un text la hover, poti pune in schimb un sablon.
"""

from __future__ import annotations

import logging
import math
import time

from ..core import humanize, vision
from ..core.engine import Behavior, BotContext

log = logging.getLogger(__name__)


class GatherBehavior(Behavior):
    name = "gather"
    priority = 60

    def __init__(self) -> None:
        self._failed_streak = 0
        self._last_attempt_at = 0.0
        self._recent_nodes: list[tuple[int, int, float]] = []

    def should_run(self, ctx: BotContext) -> bool:
        if not ctx.zone_allows("gather"):
            return False
        if time.monotonic() - self._last_attempt_at < 1.0:
            return False
        return bool(self._visible_nodes(ctx))

    def run(self, ctx: BotContext) -> None:
        section = ctx.profile.section("gather")
        nodes = self._visible_nodes(ctx)
        if not nodes:
            return

        self._last_attempt_at = time.monotonic()
        cx, cy = ctx.screen_center()
        target = min(nodes, key=lambda b: math.hypot(b.center[0] - cx, b.center[1] - cy))
        tx, ty = target.center

        ctx.controller.click(tx, ty)
        humanize.sleep(float(section.get("click_delay", 0.6)), 0.25)

        # Unele jocuri cer si o tasta de interactiune dupa selectie.
        interact = ctx.profile.key("interact")
        if interact:
            ctx.controller.key(str(interact))

        cast_seconds = float(section.get("cast_seconds", 3.0))
        if self._wait_for_cast(ctx, cast_seconds):
            ctx.stats.gathers += 1
            self._failed_streak = 0
            self._remember(tx, ty)
            print(f"  + resursa culeasa (total {ctx.stats.gathers})")
        else:
            self._failed_streak += 1
            self._remember(tx, ty)
            log.debug("Cules esuat (%d la rand).", self._failed_streak)
            if self._failed_streak >= int(section.get("max_failures", 4)):
                # Nodul e probabil in spatele unei stanci sau prea departe.
                # Ne oprim din incercat si lasam traseul sa ne duca mai departe.
                print("  ~ nu ajung la noduri aici, merg mai departe")
                ctx.dwell_until = 0.0
                self._failed_streak = 0

    # ------------------------------------------------------------- ajutator

    def _visible_nodes(self, ctx: BotContext) -> list:
        """Nodurile de pe ecran, minus cele incercate recent fara succes."""
        section = ctx.profile.section("gather")
        blobs = ctx.find_blobs(
            "resource_node",
            region_name=section.get("search_region"),
            min_area=int(section.get("min_area", 80)),
        )
        if not blobs:
            return []

        now = time.monotonic()
        forget_after = float(section.get("blacklist_seconds", 25.0))
        self._recent_nodes = [n for n in self._recent_nodes if now - n[2] < forget_after]

        def is_recent(blob) -> bool:
            bx, by = blob.center
            return any(math.hypot(bx - x, by - y) < 45 for x, y, _ in self._recent_nodes)

        return [b for b in blobs if not is_recent(b)]

    def _remember(self, x: int, y: int) -> None:
        """Tine minte nodurile atinse, ca sa nu ne blocam pe acelasi la infinit."""
        self._recent_nodes.append((x, y, time.monotonic()))

    def _wait_for_cast(self, ctx: BotContext, seconds: float) -> bool:
        """Asteapta terminarea culesului si spune daca pare sa fi reusit.

        Daca profilul defineste `regions.cast_bar`, ne uitam la ea: culesul a
        reusit daca bara a aparut si apoi a disparut. Altfel asteptam pur si
        simplu durata din profil si presupunem ca a mers.
        """
        cast_region = ctx.profile.region("cast_bar")
        cast_color = ctx.profile.color("cast_bar")
        deadline = time.monotonic() + seconds + 2.0

        if cast_region is None or cast_color is None:
            humanize.sleep(seconds, 0.15)
            return True

        seen_bar = False
        while time.monotonic() < deadline:
            if not ctx.running():
                return False
            ctx.refresh()
            crop = ctx.crop("cast_bar")
            if crop is None:
                break
            fill = vision.bar_fill_ratio(crop, cast_color.low, cast_color.high)
            if fill > 0.05:
                seen_bar = True
            elif seen_bar:
                return True  # bara a aparut si s-a incheiat
            time.sleep(0.15)

        return seen_bar
