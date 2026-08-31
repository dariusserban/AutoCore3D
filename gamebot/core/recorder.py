"""Modul de invatare: tu joci, botul se uita si isi noteaza harta.

Asculta tastatura si mouse-ul in timp ce parcurgi tu traseul si scrie fiecare
eveniment cu decalajul lui real. Cand apesi o tasta de reper, taie stream-ul si
salveaza o ancora vizuala (o poza cu minimapa) pentru locul in care esti.

Portalele sunt tratate separat, fiindca nu pot fi redate ca un click obisnuit:
ecranul de incarcare dureaza de fiecare data altcat. Marchezi portalul, dai
click pe el, iar recorder-ul asteapta sa se incarce harta noua si retine cum
arata - ca botul sa poata confirma mai tarziu ca a ajuns unde trebuie.

Taste implicite - toate se pot schimba in profil, sub `record:`, daca jocul
foloseste deja tastele astea:
  F4  portal (urmatorul click e pe portal)   F5  reper de drum
  F6  reper de lupta                         F7  reper de resurse
  F8  reper de vendor/reparat
  F9  pauza / reluare                        F10 opreste si salveaza
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Optional

from . import vision
from .capture import Region, ScreenCapture
from .route import InputEvent, Portal, Route, Waypoint

log = logging.getLogger(__name__)

# Sub pragurile astea nu inregistram miscarea mouse-ului. Fara ele, o singura
# tura de 10 minute produce zeci de mii de evenimente inutile.
MOVE_MIN_INTERVAL = 0.03  # secunde
MOVE_MIN_DISTANCE = 6  # pixeli

# Latimea la care salvam ancorele. Cand `regions.minimap` lipseste, ancora e
# tot ecranul jocului, iar la marimea reala ar insemna sute de megaocteti pe
# ruta si o comparatie inutil de lenta.
ANCHOR_WIDTH = 240

DEFAULT_HOTKEYS = {
    "f4": "portal",
    "f5": "travel",
    "f6": "combat",
    "f7": "gather",
    "f8": "vendor",
}
DEFAULT_PAUSE_KEY = "f9"
DEFAULT_STOP_KEY = "f10"


class RouteRecorder:
    """Inregistreaza o ruta. Blocheaza pana apesi tasta de oprire.

    Ascultatorii pynput ruleaza pe firele lor, dar nu fac niciodata captura de
    ecran: `mss` nu e sigur intre fire. Firele de input doar pun cereri intr-o
    coada, iar firul principal - cel din `run()` - face toate capturile.
    """

    def __init__(
        self,
        name: str,
        output_dir: str | Path,
        capture: Optional[ScreenCapture] = None,
        anchor_region: Optional[Region] = None,
        hotkeys: Optional[dict[str, str]] = None,
        pause_key: str = DEFAULT_PAUSE_KEY,
        stop_key: str = DEFAULT_STOP_KEY,
        record_mouse_moves: bool = True,
        stop_file: Optional[str | Path] = None,
    ) -> None:
        self.name = name
        self.output_dir = Path(output_dir)
        self.capture = capture
        self.anchor_region = anchor_region
        self.hotkeys = {str(k).lower(): v for k, v in (hotkeys or DEFAULT_HOTKEYS).items()}
        self.pause_key = pause_key.lower()
        self.stop_key = stop_key.lower()
        self.record_mouse_moves = record_mouse_moves
        # Butonul OPRESTE din fereastra lasa fisierul asta pe disc. Il tratam
        # exact ca pe tasta de stop: inchidem si SALVAM. Inainte, butonul doar
        # omora procesul, deci toata tura inregistrata se pierdea.
        self.stop_file = Path(stop_file) if stop_file else None

        conflict = self.hotkeys.keys() & {self.pause_key, self.stop_key}
        if conflict:
            raise ValueError(
                f"Tasta {', '.join(sorted(conflict))} e folosita si pentru reper, si pentru "
                "control. Schimba una dintre ele in profil, sub `record:`."
            )

        self.route = Route(name=name, waypoints=[])
        self._events: list[InputEvent] = []
        self._lock = threading.Lock()
        self._mark_queue: queue.Queue[str] = queue.Queue()

        self._last_event_at = 0.0
        self._last_move_at = 0.0
        self._last_move_pos = (0, 0)
        self._paused = False
        self._running = False

        # Starea tranzitiei prin portal.
        self._awaiting_portal: Optional[Waypoint] = None
        self._portal_click: Optional[tuple[int, int]] = None
        self._suppress_mouse_up = False
        self._loading_portal: Optional[Waypoint] = None
        # Reperul care asteapta sa i se faca poza, la prima actiune din joc.
        self._anchor_in_asteptare: Optional[Waypoint] = None

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

    def _are_actiuni(self) -> bool:
        with self._lock:
            return bool(self._events)

    def _record(self, event: InputEvent) -> None:
        if self._paused or not self._running:
            return
        with self._lock:
            self._events.append(event)

    # -------------------------------------------------------------- repere

    def mark_waypoint(self, kind: str, label: str = "") -> Waypoint:
        """Inchide segmentul curent si incepe unul nou.

        Se apeleaza doar din firul principal: face captura de ecran.
        Evenimentele acumulate pana acum devin drumul *catre* acest reper, deci
        le atasam reperului anterior.
        """
        index = len(self.route.waypoints)
        with self._lock:
            if self.route.waypoints:
                self.route.waypoints[-1].events = self._events
            self._events = []

        anchor_name = self._save_anchor(f"anchor_{index:03d}.png")
        waypoint = Waypoint(index=index, kind=kind, label=label, anchor=anchor_name)
        self.route.waypoints.append(waypoint)

        if kind == "portal":
            self._awaiting_portal = waypoint
            print(f"  [{index:>3}] PORTAL marcat - da click pe portal acum")
        else:
            print(f"  [{index:>3}] reper '{kind}' salvat")

        log.info("Reper %d marcat (%s)%s", index, kind, f" - {label}" if label else "")
        return waypoint

    def start_recording(self) -> Waypoint:
        """Deschide reperul zero, in care intra tot ce faci de acum inainte.

        Poza de referinta a acestui reper NU se ia acum, ci la prima ta actiune
        in joc. Daca am lua-o imediat, ar prinde fereastra aplicatiei - te uiti
        inca la ea cand apesi butonul. Amanand-o pana misti tu ceva, stim ca
        esti deja in joc, si nu mai e nevoie de nicio numaratoare inversa.
        """
        waypoint = Waypoint(index=0, kind="travel", label="start")
        self.route.waypoints.append(waypoint)
        self._anchor_in_asteptare = waypoint
        return waypoint

    def _save_anchor(self, filename: str) -> Optional[str]:
        """Poza de referinta (de obicei minimapa). Doar din firul principal."""
        if self.capture is None:
            return None
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.capture.save(self.output_dir / filename, self.anchor_region,
                              width=ANCHOR_WIDTH)
            return filename
        except Exception as exc:  # o ancora lipsa nu trebuie sa strice ruta
            log.warning("Nu am putut salva ancora '%s': %s", filename, exc)
            return None

    # -------------------------------------------------------------- portal

    def _finish_portal(self, waypoint: Waypoint) -> None:
        """Asteapta incarcarea hartii noi si retine cum arata.

        Doua faze: intai asteptam ca ecranul sa se schimbe masiv (a inceput
        incarcarea), apoi ca doua cadre consecutive sa devina aproape identice
        (s-a terminat). Daca nu prindem faza intai - portalele instantanee
        exista - trecem oricum la stabilizare, ca sa nu blocam inregistrarea.
        """
        click = self._portal_click or (0, 0)
        waypoint.portal = Portal(click=click)
        self._loading_portal = None
        self._portal_click = None

        if self.capture is None:
            print("      (fara captura: portalul se va reda dupa timp fix)")
            self._last_event_at = time.monotonic()
            return

        print("      astept incarcarea hartii...")
        started = time.monotonic()
        baseline = self.capture.grab(self.anchor_region)

        # Faza 1: a inceput incarcarea?
        while time.monotonic() - started < 8.0:
            time.sleep(0.25)
            if vision.frames_differ(baseline, self.capture.grab(self.anchor_region), 12.0):
                break

        # Faza 2: s-a linistit ecranul?
        stable_since = 0.0
        previous = self.capture.grab(self.anchor_region)
        while time.monotonic() - started < 45.0:
            time.sleep(0.3)
            current = self.capture.grab(self.anchor_region)
            if vision.frames_differ(previous, current, 3.0):
                stable_since = 0.0
            elif stable_since == 0.0:
                stable_since = time.monotonic()
            elif time.monotonic() - stable_since > 1.5:
                break
            previous = current

        elapsed = time.monotonic() - started
        waypoint.portal.load_seconds = round(max(5.0, elapsed * 2.0), 1)
        waypoint.portal.dest_anchor = self._save_anchor(f"portal_{waypoint.index:03d}_dest.png")

        print(f"      harta noua incarcata in {elapsed:.1f}s - continua traseul")
        # Timpul de incarcare nu trebuie sa devina o pauza in secventa redata.
        self._last_event_at = time.monotonic()

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
        self.start_recording()

        def on_press(key):
            name = self._key_name(key)
            if name is None:
                return
            if self._handle_control_key(name):
                return  # tastele de control nu intra in ruta
            self._record(InputEvent("key_down", self._dt(), key=name))

        def on_release(key):
            name = self._key_name(key)
            if name is None or name in self.hotkeys or name in (self.pause_key, self.stop_key):
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
            # Clicul pe portal nu intra in secventa redata: de el se ocupa
            # comportamentul de portal, care stie sa astepte incarcarea.
            if pressed and self._awaiting_portal is not None:
                self._portal_click = (int(x), int(y))
                self._loading_portal = self._awaiting_portal
                self._awaiting_portal = None
                self._suppress_mouse_up = True
                return
            if not pressed and self._suppress_mouse_up:
                self._suppress_mouse_up = False
                return

            kind = "mouse_down" if pressed else "mouse_up"
            self._record(InputEvent(kind, self._dt(), x=int(x), y=int(y), button=button.name))

        def on_scroll(x, y, dx, dy):
            self._record(InputEvent("scroll", self._dt(), amount=int(dy)))

        kb = keyboard.Listener(on_press=on_press, on_release=on_release)
        ms = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
        kb.start()
        ms.start()

        try:
            self._main_loop()
        except KeyboardInterrupt:
            print("\nOprit de la tastatura.")
        finally:
            kb.stop()
            ms.stop()

        return self._finalize()

    def _main_loop(self) -> None:
        """Firul principal: singurul care are voie sa faca captura de ecran."""
        ultimul_semn = time.monotonic()

        while self._running:
            while not self._mark_queue.empty():
                self.mark_waypoint(self._mark_queue.get())

            if self._anchor_in_asteptare is not None and self._are_actiuni():
                reper = self._anchor_in_asteptare
                self._anchor_in_asteptare = None
                reper.anchor = self._save_anchor(f"anchor_{reper.index:03d}.png")
                print("  inregistrez... (F10 cand ai terminat tura)", flush=True)

            if self._loading_portal is not None:
                self._finish_portal(self._loading_portal)

            if self.stop_file is not None and self.stop_file.exists():
                print("  oprire ceruta din fereastra - salvez ruta", flush=True)
                self._running = False
                break

            # Semn de viata: fara el, cine se uita la jurnal nu are cum sa stie
            # daca inregistrarea merge sau daca s-a blocat ceva.
            if time.monotonic() - ultimul_semn >= 5.0:
                ultimul_semn = time.monotonic()
                with self._lock:
                    in_curs = len(self._events)
                total = sum(len(w.events) for w in self.route.waypoints) + in_curs
                stare = "PAUZA" if self._paused else "inregistrez"
                print(f"  [{stare}] {len(self.route.waypoints)} repere, "
                      f"{total} actiuni captate", flush=True)

            time.sleep(0.05)

    def _handle_control_key(self, name: str) -> bool:
        """Trateaza tastele de comanda. Intoarce True daca a consumat tasta."""
        if name in self.hotkeys:
            # Marcarea face captura de ecran, deci o lasam pe seama firului
            # principal; aici doar punem cererea la coada.
            self._mark_queue.put(self.hotkeys[name])
            return True
        if name == self.pause_key:
            self._paused = not self._paused
            print("  >> inregistrare in PAUZA" if self._paused else "  >> inregistrare reluata")
            self._last_event_at = time.monotonic()
            return True
        if name == self.stop_key:
            self._running = False
            return True
        return False

    def _finalize(self) -> Route:
        """Ataseaza ultimul segment, completeaza metadatele si salveaza."""
        with self._lock:
            if self.route.waypoints:
                self.route.waypoints[-1].events = self._events
            elif not self.route.waypoints:
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
        print(f"Control: {self.pause_key.upper()}=pauza  {self.stop_key.upper()}=stop si salveaza")
        print("\nINREGISTREZ DEJA. Comuta pe joc si joaca normal -")
        print("fiecare miscare, click si tasta se salveaza automat.")
        print(f"\nCand ai terminat tura: {self.stop_key.upper()}")
        print("\nOptional, ca botul sa se descurce mai bine:")
        print("  F6 unde vrei sa se bata   F4 inainte de click pe portal")
        print("  F5 la cotituri importante\n", flush=True)
