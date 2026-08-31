"""Urcatul pe montura, ca sa nu se plimbe pe jos intre zonele de farmat.

Din pixeli nu putem sti sigur daca esti deja calare - jocul nu ne spune. Avem
doua feluri de a ne descurca, si le folosim pe amandoua cat se poate:

  - daca ai calibrat un sablon `mounted` (o iconita care apare doar cand esti
    calare), ne uitam la el si stim sigur;
  - daca nu, apasam tasta de montura din cand in cand, cat timp mergem si nu e
    nimic de batut. In majoritatea jocurilor o apasare in plus cand esti deja
    calare nu strica nimic.

Nu urcam niciodata in mijlocul unei lupte: comportamentul de lupta are
prioritate mai mare si oricum nu am apuca, iar in multe jocuri incercarea
intrerupe atacul.
"""

from __future__ import annotations

import logging
import time

from ..core import humanize, vision
from ..core.engine import Behavior, BotContext

log = logging.getLogger(__name__)


class MountBehavior(Behavior):
    name = "mount"
    priority = 20  # sub intretinere, peste mersul propriu-zis

    def __init__(self) -> None:
        self._last_attempt = 0.0

    def enabled(self, ctx: BotContext) -> bool:
        return ctx.profile.enabled("mount") and bool(ctx.profile.key("mount"))

    def should_run(self, ctx: BotContext) -> bool:
        section = ctx.profile.section("mount")

        # Nu urcam cand stationam intr-o zona de farmat: acolo ne batem.
        if ctx.dwelling():
            return False

        # Nici cand e ceva langa noi - intai se rezolva lupta.
        from .combat import CombatBehavior

        if CombatBehavior._enemies(ctx):
            return False

        if time.monotonic() - self._last_attempt < float(section.get("retry_seconds", 25.0)):
            return False

        return not self._is_mounted(ctx)

    def run(self, ctx: BotContext) -> None:
        key = str(ctx.profile.key("mount"))
        self._last_attempt = time.monotonic()

        ctx.controller.key(key)
        # Urcarea are o animatie; daca plecam imediat, o intrerupem singuri.
        humanize.sleep(float(ctx.profile.section("mount").get("cast_seconds", 2.0)), 0.2)
        log.debug("Am apasat tasta de montura (%s).", key)

    def _is_mounted(self, ctx: BotContext) -> bool:
        """Sablonul `mounted`, daca exista. Altfel nu avem de unde sti."""
        if not ctx.templates.has("mounted") or ctx.frame is None:
            return False
        match = vision.find_template(
            ctx.frame,
            ctx.templates["mounted"],
            ctx.profile.threshold("template_match", 0.85),
        )
        return match is not None
