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

        self._pregateste_culesul(ctx, player)

        if ctx.needs_resync:
            ctx.needs_resync = False
            if not player.resync():
                print("  !! nu ma pot reorienta dupa lupta - opresc")
                ctx.kill_switch.stop("nu recunosc pozitia dupa lupta")
                return

        before_laps = player.laps
        before_lost = player.lost_count

        waypoint = player.advance()
        if waypoint is None:
            if not ctx.kill_switch.stopped:
                print("  !! nu ma mai pot orienta pe traseu - opresc")
                ctx.kill_switch.stop("nu recunosc pozitia pe traseu")
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

    # ------------------------------------------------- culesul din mers

    def _pregateste_culesul(self, ctx: BotContext, player) -> None:
        """Leaga culesul de redarea segmentului.

        Un segment se reda dintr-o bucata, iar o ruta cu putine repere e un
        segment cat toata tura. Fara asta, botul ar trece pe langa tot ce e pe
        jos si ar aduna abia la capat, cand obiectele au disparut demult.
        """
        cules = ctx.behaviors.get("loot")
        if cules is None:
            player.on_tick = None
            return

        player.tick_interval = float(ctx.profile.section("loot").get("interval", 1.0))

        def culege():
            # Aceeasi instanta ca a motorului, deci aceeasi lista neagra: un
            # obiect de neluat nu e reincercat la fiecare pas.
            ctx.refresh()
            if cules.should_run(ctx):
                cules.run(ctx)

        player.on_tick = culege
