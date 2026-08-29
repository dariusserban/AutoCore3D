"""Modul de invatare: tu joci, botul se uita si isi noteaza harta.

Asculta tastatura si mouse-ul in timp ce parcurgi tu traseul si scrie fiecare
eveniment cu decalajul lui real. Cand apesi o tasta de reper, taie stream-ul si
salveaza o ancora vizuala (o poza cu minimapa) pentru locul in care esti.

Rezultatul e un director de ruta pe care `player.py` il poate reda apoi la
nesfarsit.

Taste implicite (se pot schimba in profil):
  F5  reper de drum         F6  reper de lupta
  F7  reper de resurse      F8  reper de vendor/reparat
  F9  pauza / reluare       F10 opreste si salveaza
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from .capture import Region, ScreenCapture
from .route import InputEvent, Route, Waypoint

log = logging.getLogger(__name__)

# Sub pragurile astea nu inregistram miscarea mouse-ului. Fara ele, o singura
# tura de 10 minute produce zeci de mii de evenimente inutile.
MOVE_MIN_INTERVAL = 0.03  # secunde
MOVE_MIN_DISTANCE = 6  # pixeli

DEFAULT_HOTKEYS = {
    "f5": "travel",
    "f6": "combat",
    "f7": "gather",
    "f8": "vendor",
}
PAUSE_KEY = "f9"
STOP_KEY = "f10"


class RouteRecorder:
    """Inregistreaza o ruta. Blocheaza pana apesi tasta de oprire."""

    def __init__(
        self,
        name: str,
        output_dir: str | Path,
        capture: Optional[ScreenCapture] = None,
        anchor_region: Optional[Region] = None,
        hotkeys: Optional[dict[str, str]] = None,
        record_mouse_moves: bool = True,
    ) -> None:
        self.name = name
        self.output_dir = Path(output_dir)
        self.capture = capture
        self.anchor_region = anchor_region
        self.hotkeys = {k.lower(): v for k, v in (hotkeys or DEFAULT_HOTKEYS).items()}
        self.record_mouse_moves = record_mouse_moves

        self.route = Route(name=name, waypoints=[])
        self._events: list[InputEvent] = []
        self._last_event_at = 0.0
        self._last_move_at = 0.0
        self._last_move_pos = (0, 0)
        self._paused = False
        self._running = False
        self._waypoint_marked_at = 0.0

    # ------------------------------------------------------------ ajutatoare

    def _dt(self) -> float:
        """Timpul scurs de la evenimentul anterior, in secunde."""
        now = time.monotonic()
        if self._last_event_at == 0.0:
            self._last_event_at = now
            return 0.0
        dt = now - self._last_event_at
        self._last_event_at = now
        # Daca stai 3 minute pe loc sa citesti ceva, nu vrem ca botul sa
        # reproduca fidel pauza aia la fiecare tura.
        return min(dt, 5.0)

    @staticmethod
    def _key_name(key) -> Optional[str]:
        """Traduce obiectul pynput intr-un nume acceptat de pydirectinput."""
        try:
            from pynput import keyboard
        except Exception:  # pragma: no cover
            return None
        if isinstance(key, keyboard.KeyCode):
            return key.char.lower() if key.char else None
        if isinstance(key, keyboard.Key):
            return key.name.lower()
        return None

    def _record(self, event: InputEvent) -> None:
        if not self._paused and self._running:
            self._events.append(event)

    # -------------------------------------------------------------- repere

    def mark_waypoint(self, kind: str, label: str = "") -> Waypoint:
        """Inchide segmentul curent si incepe unul nou.

        Evenimentele acumulate pana acum devin drumul *catre* acest reper, deci
        le atasam reperului anterior. Primul reper porneste cu lista goala.
        """
        index = len(self.route.waypoints)
        if self.route.waypoints:
            self.route.waypoints[-1].events = self._events
        self._events = []

        anchor_name = self._save_anchor(index)
        waypoint = Waypoint(index=index, kind=kind, label=label, anchor=anchor_name)
        self.route.waypoints.append(waypoint)
        self._waypoint_marked_at = time.monotonic()

        log.info("Reper %d marcat (%s)%s", index, kind, f" - {label}" if label else "")
        print(f"  [{index:>3}] reper '{kind}' salvat")
        return waypoint

    def _save_anchor(self, index: int) -> Optional[str]:
        """Poza de referinta pentru reperul curent (de obicei minimapa)."""
        if self.capture is None:
            return None
        try:
            filename = f"anchor_{index:03d}.png"
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.capture.save(self.output_dir / filename, self.anchor_region)
            return filename
        except Exception as exc:  # o ancora lipsa nu trebuie sa strice ruta
            log.warning("Nu am putut salva ancora pentru reperul %d: %s", index, exc)
            return None

    # ------------------------------------------------------------- rulare

    def run(self) -> Route:
        """Porneste ascultatorii si tine sesiunea pana la tasta de oprire."""
        try:
            from pynput import keyboard, mouse
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "pynput nu e instalat. pip install -r gamebot/requirements.txt"
            ) from exc

        self._running = True
        self._last_event_at = time.monotonic()
        self._print_banner()

        def on_press(key):
            name = self._key_name(key)
            if name is None:
                return
            if self._handle_control_key(name):
                return  # tastele de control nu intra in ruta
            self._record(InputEvent("key_down", self._dt(), key=name))

        def on_release(key):
            name = self._key_name(key)
            if name is None or name in self.hotkeys or name in (PAUSE_KEY, STOP_KEY):
                return
            self._record(InputEvent("key_up", self._dt(), key=name))

        def on_move(x, y):
            if not self.record_mouse_moves:
                return
            now = time.monotonic()
            dist = abs(x - self._last_move_pos[0]) + abs(y - self._last_move_pos[1])
            if now - self._last_move_at < MOVE_MIN_INTERVAL or dist < MOVE_MIN_DISTANCE:
                return
            self._last_move_at = now
            self._last_move_pos = (int(x), int(y))
            self._record(InputEvent("move", self._dt(), x=int(x), y=int(y)))

        def on_click(x, y, button, pressed):
            kind = "mouse_down" if pressed else "mouse_up"
            self._record(
                InputEvent(kind, self._dt(), x=int(x), y=int(y), button=button.name)
            )

        def on_scroll(x, y, dx, dy):
            self._record(InputEvent("scroll", self._dt(), amount=int(dy)))

        kb = keyboard.Listener(on_press=on_press, on_release=on_release)
        ms = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
        kb.start()
        ms.start()

        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nOprit de la tastatura.")
        finally:
            kb.stop()
            ms.stop()

        return self._finalize()

    def _handle_control_key(self, name: str) -> bool:
        """Trateaza tastele de comanda. Intoarce True daca a consumat tasta."""
        if name in self.hotkeys:
            self.mark_waypoint(self.hotkeys[name])
            return True
        if name == PAUSE_KEY:
            self._paused = not self._paused
            print("  >> inregistrare in PAUZA" if self._paused else "  >> inregistrare reluata")
            self._last_event_at = time.monotonic()
            return True
        if name == STOP_KEY:
            self._running = False
            return True
        return False

    def _finalize(self) -> Route:
        """Ataseaza ultimul segment, completeaza metadatele si salveaza."""
        if self.route.waypoints:
            self.route.waypoints[-1].events = self._events
        else:
            print("Nu ai marcat niciun reper - ruta e goala, nu salvez nimic.")
            return self.route

        if self.capture is not None:
            monitor = self.capture.monitor
            self.route.screen = {"width": monitor.width, "height": monitor.height}

        self.route.save(self.output_dir)
        print("\n" + self.route.describe())
        print(f"Salvat in: {self.output_dir}")
        return self.route

    def _print_banner(self) -> None:
        keys = "  ".join(f"{k.upper()}={v}" for k, v in self.hotkeys.items())
        print("\n=== INREGISTRARE RUTA ===")
        print(f"Ruta: {self.name}")
        print(f"Repere:  {keys}")
        print(f"Control: {PAUSE_KEY.upper()}=pauza  {STOP_KEY.upper()}=stop si salveaza")
        print("\nIntra in joc si mergi traseul. Marcheaza un reper la fiecare")
        print("colt, la fiecare zona de farmat si la fiecare NPC important.")
        print("Cu cat pui mai multe repere, cu atat botul se corecteaza mai bine.\n")
