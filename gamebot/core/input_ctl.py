"""Trimiterea de taste si miscari de mouse catre joc.

De ce pydirectinput si nu pyautogui: jocurile care citesc input prin DirectInput
(majoritatea MMO-urilor 3D) ignora evenimentele sintetice trimise de pyautogui
prin SendInput cu flag-uri de mouse "de fereastra". pydirectinput trimite scan
codes de tastatura si evenimente de mouse la nivel mai jos, pe care jocul le
vede. Pe Linux nu exista pydirectinput, deci cadem pe pyautogui.

Toate metodele trec prin `humanize`, ca sa nu iasa doua actiuni identice la
milisecunda.
"""

from __future__ import annotations

import logging
import platform
import time
from typing import Optional, Protocol

from . import humanize

log = logging.getLogger(__name__)


class Backend(Protocol):
    """Interfata minima pe care o cere controllerul de la un backend de input."""

    def move_to(self, x: int, y: int) -> None: ...
    def mouse_down(self, button: str) -> None: ...
    def mouse_up(self, button: str) -> None: ...
    def key_down(self, key: str) -> None: ...
    def key_up(self, key: str) -> None: ...
    def scroll(self, clicks: int) -> None: ...
    def position(self) -> tuple[int, int]: ...


class NullBackend:
    """Nu trimite nimic; doar noteaza ce s-ar fi trimis.

    Modul asta (--dry-run) e felul corect de a testa un bot: vezi ce decizii ia
    fara ca personajul sa se miste in joc.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []
        self._pos = (0, 0)

    def move_to(self, x: int, y: int) -> None:
        self._pos = (x, y)
        self.events.append(("move", (x, y)))

    def mouse_down(self, button: str) -> None:
        self.events.append(("mouse_down", button))

    def mouse_up(self, button: str) -> None:
        self.events.append(("mouse_up", button))

    def key_down(self, key: str) -> None:
        self.events.append(("key_down", key))

    def key_up(self, key: str) -> None:
        self.events.append(("key_up", key))

    def scroll(self, clicks: int) -> None:
        self.events.append(("scroll", clicks))

    def position(self) -> tuple[int, int]:
        return self._pos


class DirectInputBackend:
    """Backend real. Prefera pydirectinput, cade pe pyautogui daca lipseste."""

    def __init__(self) -> None:
        self._impl = None
        try:
            import pydirectinput

            pydirectinput.PAUSE = 0.0  # temporizarea o facem noi, umanizat
            pydirectinput.FAILSAFE = False  # avem kill switch propriu
            self._impl = pydirectinput
            self.name = "pydirectinput"
        except Exception:
            import pyautogui

            pyautogui.PAUSE = 0.0
            pyautogui.FAILSAFE = False
            self._impl = pyautogui
            self.name = "pyautogui"
            if platform.system() == "Windows":
                log.warning(
                    "pydirectinput lipseste; pe Windows multe jocuri vor ignora "
                    "input-ul trimis de pyautogui."
                )

    def move_to(self, x: int, y: int) -> None:
        self._impl.moveTo(x, y)

    def mouse_down(self, button: str) -> None:
        self._impl.mouseDown(button=button)

    def mouse_up(self, button: str) -> None:
        self._impl.mouseUp(button=button)

    def key_down(self, key: str) -> None:
        self._impl.keyDown(key)

    def key_up(self, key: str) -> None:
        self._impl.keyUp(key)

    def scroll(self, clicks: int) -> None:
        self._impl.scroll(clicks)

    def position(self) -> tuple[int, int]:
        pos = self._impl.position()
        return int(pos[0]), int(pos[1])


class InputController:
    """Trimite input umanizat si tine minte ce a trimis.

    `click_radius` imprastie clicurile in jurul tintei, `move_speed` scaleaza
    durata totala a unei miscari de mouse.
    """

    def __init__(
        self,
        backend: Optional[Backend] = None,
        click_radius: int = 3,
        move_speed: float = 1.0,
        dry_run: bool = False,
    ) -> None:
        self.backend: Backend = backend or (NullBackend() if dry_run else DirectInputBackend())
        self.dry_run = dry_run
        self.click_radius = click_radius
        self.move_speed = max(0.1, move_speed)
        self._held_keys: set[str] = set()
        self.actions_sent = 0

    # ---------------------------------------------------------------- mouse

    def move(self, x: int, y: int, curvature: float = 0.18) -> None:
        """Muta cursorul pe o traiectorie curbata, nu instantaneu."""
        start = self.backend.position()
        path = humanize.mouse_path((int(start[0]), int(start[1])), (int(x), int(y)), curvature)
        # Distribuim ~1.5 px/ms peste toti pasii, deci miscarile lungi dureaza
        # proportional mai mult, ca la o mana adevarata.
        step_delay = (0.012 / self.move_speed)
        for px, py in path:
            self.backend.move_to(px, py)
            if not self.dry_run:
                time.sleep(humanize.delay(step_delay, 0.3))
        self.actions_sent += 1

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        double: bool = False,
    ) -> None:
        """Click, optional dupa o mutare pe pozitie."""
        if x is not None and y is not None:
            tx, ty = humanize.jitter_point(int(x), int(y), self.click_radius)
            self.move(tx, ty)
            self._pause(0.05)

        for i in range(2 if double else 1):
            self.backend.mouse_down(button)
            time.sleep(humanize.hold_time(0.055))
            self.backend.mouse_up(button)
            if double and i == 0:
                time.sleep(humanize.delay(0.07, 0.2))
        self.actions_sent += 1

    def drag(self, from_xy: tuple[int, int], to_xy: tuple[int, int], button: str = "left") -> None:
        """Tine apasat si trage. Folosit pentru rotirea camerei cu butonul drept."""
        self.move(*from_xy)
        self.backend.mouse_down(button)
        self._pause(0.08)
        self.move(*to_xy, curvature=0.05)
        self._pause(0.08)
        self.backend.mouse_up(button)
        self.actions_sent += 1

    def scroll(self, clicks: int) -> None:
        self.backend.scroll(clicks)
        self.actions_sent += 1

    # ------------------------------------------------------------- tastatura

    def key(self, key: str) -> None:
        """O apasare completa, cu durata de tinere variabila."""
        self.backend.key_down(key)
        time.sleep(humanize.hold_time())
        self.backend.key_up(key)
        self.actions_sent += 1

    def key_sequence(self, keys: list[str], gap: float = 0.12) -> None:
        for k in keys:
            self.key(k)
            self._pause(gap)

    def hold(self, key: str, duration: float) -> None:
        """Tine o tasta apasata (mers inainte, de exemplu)."""
        self.backend.key_down(key)
        self._held_keys.add(key)
        try:
            time.sleep(max(0.0, duration))
        finally:
            self.backend.key_up(key)
            self._held_keys.discard(key)
        self.actions_sent += 1

    def key_down(self, key: str) -> None:
        self.backend.key_down(key)
        self._held_keys.add(key)

    def key_up(self, key: str) -> None:
        self.backend.key_up(key)
        self._held_keys.discard(key)

    def release_all(self) -> None:
        """Elibereaza tot ce e apasat.

        Obligatoriu la oprire: daca botul moare cu 'w' apasat, personajul
        continua sa mearga in perete dupa ce tu ai luat mana de pe tastatura.
        """
        for key in list(self._held_keys):
            try:
                self.backend.key_up(key)
            except Exception:
                pass
        self._held_keys.clear()

    # ---------------------------------------------------------------- intern

    def _pause(self, base: float) -> None:
        if not self.dry_run:
            time.sleep(humanize.delay(base, 0.3))
