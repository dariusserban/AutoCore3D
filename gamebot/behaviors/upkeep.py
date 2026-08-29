"""Intretinere periodica: vinde gunoiul, repara, ia recompensele zilnice.

Secventa e complet declarativa, in profil, fiindca meniurile difera de la joc
la joc. Un pas poate fi: apasa o tasta, da click intr-un punct, sau cauta un
sablon pe ecran si da click pe el.
"""

from __future__ import annotations

import logging
import time

from ..core import humanize, vision
from ..core.engine import Behavior, BotContext

log = logging.getLogger(__name__)


class UpkeepBehavior(Behavior):
    name = "upkeep"
    priority = 40

    def __init__(self) -> None:
        self._last_run_at = time.monotonic()

    def should_run(self, ctx: BotContext) -> bool:
        section = ctx.profile.section("upkeep")
        interval = float(section.get("every_minutes", 30.0)) * 60.0
        if time.monotonic() - self._last_run_at < interval:
            return False
        # Rulam intretinerea doar unde are sens: la reperele de vendor sau de
        # reparat. Cu `at_waypoint_only: false` merge oriunde - potrivit pentru
        # secvente care nu au nevoie de NPC, cum sunt recompensele zilnice.
        if not section.get("at_waypoint_only", True):
            return True
        return ctx.current_waypoint is not None and ctx.zone_allows("upkeep")

    def run(self, ctx: BotContext) -> None:
        steps = ctx.profile.section("upkeep").get("steps") or []
        if not steps:
            self._last_run_at = time.monotonic()
            return

        print("  ~ rulez intretinerea (vanzare / reparat / daily)")
        for step in steps:
            if not ctx.running():
                break
            self._execute(ctx, step)

        self._last_run_at = time.monotonic()
        ctx.stats.upkeep_runs += 1

    def _execute(self, ctx: BotContext, step: dict) -> None:
        """Un pas din secventa. Tipurile suportate sunt documentate in profil."""
        wait = float(step.get("wait", 0.8))

        if "key" in step:
            ctx.controller.key(str(step["key"]))

        elif "click" in step:
            x, y = step["click"]
            ctx.controller.click(int(x), int(y), double=bool(step.get("double", False)))

        elif "template" in step:
            name = str(step["template"])
            if not ctx.templates.has(name):
                log.warning("Pasul cere sablonul '%s', dar nu exista in templates/.", name)
                return
            ctx.refresh()
            match = vision.find_template(
                ctx.frame,
                ctx.templates[name],
                float(step.get("threshold", ctx.profile.threshold("template_match", 0.85))),
            )
            if match:
                ctx.controller.click(*match.center, double=bool(step.get("double", False)))
            elif step.get("required", False):
                log.warning("Nu gasesc '%s' pe ecran; opresc secventa de intretinere.", name)
                raise RuntimeError(f"pas obligatoriu esuat: {name}")

        elif "wait_only" in step:
            pass

        else:
            log.warning("Pas de intretinere necunoscut: %s", step)

        humanize.sleep(wait, 0.2)
