"""Mersul pe traseul inregistrat. Ce face botul cand nu are nimic mai bun de facut.

Prioritatea cea mai mica, intentionat: lupta, culesul si supravietuirea intrerup
mersul, iar cand se termina, traseul continua de unde a ramas.
"""

from __future__ import annotations

import logging
import time

from ..core import humanize
from ..core.engine import Behavior, BotContext

log = logging.getLogger(__name__)


class TravelBehavior(Behavior):
    name = "travel"
    priority = 10

    def enabled(self, ctx: BotContext) -> bool:
        # N-are sens fara ruta inregistrata.
        return ctx.profile.enabled("travel", True) and ctx.player is not None

    def should_run(self, ctx: BotContext) -> bool:
        if ctx.player is None:
            return False
        # Cand stationam la un reper ca sa farmam, nu plecam mai departe.
        return not ctx.dwelling()

    def run(self, ctx: BotContext) -> None:
        player = ctx.player
        assert player is not None

        if ctx.needs_resync:
            ctx.needs_resync = False
            if not player.resync():
                print("  !! nu ma pot reorienta dupa lupta - opresc")
                ctx.kill_switch.stop()
                return

        before_laps = player.laps
        before_lost = player.lost_count

        waypoint = player.advance()
        if waypoint is None:
            if not ctx.kill_switch.stopped:
                print("  !! nu ma mai pot orienta pe traseu - opresc")
                ctx.kill_switch.stop()
            return

        ctx.current_waypoint = waypoint
        ctx.stats.laps = player.laps
        if player.lost_count > before_lost:
            ctx.stats.recoveries += 1
        if player.laps > before_laps:
            print(f"  = tura {player.laps} incheiata | {ctx.stats.summary()}")

        # Stationarea la reper: cat timp e activa, comportamentele de lupta si
        # cules au ecranul la dispozitie, iar mersul asteapta.
        if waypoint.dwell > 0:
            ctx.dwell_until = time.monotonic() + humanize.delay(waypoint.dwell, 0.15)
            log.debug("Stationez %.1fs la reperul %d (%s).", waypoint.dwell, waypoint.index, waypoint.kind)
        else:
            ctx.dwell_until = 0.0

        if humanize.should_micro_pause(0.02):
            humanize.micro_pause()
