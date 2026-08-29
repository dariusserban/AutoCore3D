"""Bucla de click repetitiv, pentru zone de idle/clicker sau farmat pe loc.

Cel mai simplu comportament din tot setul: o secventa declarata in profil,
repetata la un interval, cu pauzele si imprecizia de rigoare.
"""

from __future__ import annotations

import time

from ..core import humanize
from ..core.engine import Behavior, BotContext


class IdleClickBehavior(Behavior):
    name = "idle_click"
    priority = 30

    def __init__(self) -> None:
        self._last_run_at = 0.0

    def should_run(self, ctx: BotContext) -> bool:
        section = ctx.profile.section("idle_click")
        if section.get("only_when_dwelling", True) and not ctx.dwelling():
            return False
        interval = float(section.get("interval_seconds", 1.5))
        return time.monotonic() - self._last_run_at >= interval

    def run(self, ctx: BotContext) -> None:
        section = ctx.profile.section("idle_click")
        actions = section.get("actions") or []
        self._last_run_at = time.monotonic()

        if not actions:
            return

        # Ordinea fixa a unei secvente scurte devine repede un tipar; cand
        # actiunile sunt independente intre ele, o amestecam.
        if section.get("shuffle", False):
            actions = humanize.shuffled(actions)

        for action in actions:
            if not ctx.running():
                return
            if "key" in action:
                ctx.controller.key(str(action["key"]))
            elif "click" in action:
                x, y = action["click"]
                ctx.controller.click(int(x), int(y), double=bool(action.get("double", False)))
            humanize.sleep(float(action.get("wait", 0.25)), 0.3)

        if humanize.should_micro_pause():
            humanize.micro_pause()
