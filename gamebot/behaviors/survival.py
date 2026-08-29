"""Sa nu murim. Prioritatea maxima, verificata inaintea oricarei alte decizii."""

from __future__ import annotations

import logging
import time

from ..core import humanize
from ..core.engine import Behavior, BotContext

log = logging.getLogger(__name__)


class SurvivalBehavior(Behavior):
    """Bea potiune, foloseste skill de vindecare, fugi sau opreste-te.

    Ordinea de reactie e in trepte, dupa cat de grava e situatia:
      viata < heal_below  -> vindecare (cu cooldown propriu, sa nu spamam)
      viata < flee_below  -> incercare de scapare (montura / skill de fuga)
      viata == 0          -> personajul e mort: numaram si lasam watchdog-ul
                             sa opreasca daca se repeta
    """

    name = "survival"
    priority = 100

    def __init__(self) -> None:
        self._last_heal_at = 0.0
        self._last_flee_at = 0.0
        self._death_reported_at = 0.0

    def enabled(self, ctx: BotContext) -> bool:
        # Fara bara de viata definita in profil nu avem cum sa judecam nimic.
        return ctx.profile.enabled("survival", True) and ctx.profile.region("health_bar") is not None

    def should_run(self, ctx: BotContext) -> bool:
        health = ctx.health
        if health is None:
            return False
        heal_below = ctx.profile.threshold("heal_below", 0.5)
        return health <= heal_below

    def run(self, ctx: BotContext) -> None:
        health = ctx.health or 0.0
        flee_below = ctx.profile.threshold("flee_below", 0.15)
        cooldown = float(ctx.profile.section("survival").get("heal_cooldown", 6.0))
        now = time.monotonic()

        if health <= 0.02:
            self._handle_death(ctx, now)
            return

        if health <= flee_below:
            self._flee(ctx, now)
            return

        if now - self._last_heal_at < cooldown:
            return  # skill-ul e pe cooldown; nu are rost sa mai apasam

        heal_key = ctx.profile.key("heal")
        if not heal_key:
            log.debug("Viata la %.0f%% dar nu e definita nicio tasta de vindecare.", health * 100)
            return

        print(f"  ! viata {health*100:.0f}% - ma vindec")
        ctx.controller.key(str(heal_key))
        self._last_heal_at = now
        ctx.stats.heals += 1
        # Lasam vindecarea sa isi faca efectul inainte de urmatoarea decizie,
        # altfel citim tot bara veche si ne vindecam de doua ori degeaba.
        humanize.sleep(float(ctx.profile.section("survival").get("heal_wait", 1.0)), 0.2)

    def _flee(self, ctx: BotContext, now: float) -> None:
        """Sub pragul critic: incercam sa iesim din lupta."""
        if now - self._last_flee_at < 10.0:
            return
        self._last_flee_at = now
        section = ctx.profile.section("survival")

        escape_key = ctx.profile.key("escape") or section.get("escape_key")
        if escape_key:
            print(f"  !! viata critica - folosesc scaparea ({escape_key})")
            ctx.controller.key(str(escape_key))
            humanize.sleep(1.5, 0.2)
            return

        if section.get("stop_on_critical", True):
            print("  !! viata critica si nicio scapare definita - opresc botul")
            ctx.kill_switch.stop()

    def _handle_death(self, ctx: BotContext, now: float) -> None:
        """Bara de viata la zero. Raportam o singura data per moarte."""
        if now - self._death_reported_at < 30.0:
            return
        self._death_reported_at = now
        ctx.watchdog.record_death()
        print("  xx personajul pare mort")

        # Reinvierea difera enorm de la joc la joc, deci nu ghicim: rulam
        # secventa din profil daca exista, altfel oprim si te lasam pe tine.
        steps = ctx.profile.section("survival").get("on_death")
        if not steps:
            ctx.kill_switch.stop()
            return
        for step in steps:
            if not ctx.running():
                return
            key = step.get("key")
            if key:
                ctx.controller.key(str(key))
            humanize.sleep(float(step.get("wait", 1.0)), 0.2)
