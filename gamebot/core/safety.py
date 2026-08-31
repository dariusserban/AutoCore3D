"""Franele. Un bot fara oprire de urgenta e o problema, nu o unealta.

Trei mecanisme independente, ca sa nu depinda totul de unul singur:

  KillSwitch  - o tasta globala care opreste tot, oricand, chiar daca jocul are
                focusul. Asculta la nivel de sistem, nu prin fereastra jocului.
  Watchdog    - detecteaza blocajele: ecran inghetat, prea multe morti, zero
                progres. Opreste inainte sa se strice ceva.
  SessionGuard- limite de timp si pauze programate.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import humanize, vision

log = logging.getLogger(__name__)


class KillSwitch:
    """Tasta de panica. Implicit F12.

    Ruleaza pe firul lui pynput, deci raspunde si cand bucla principala e
    blocata intr-un sleep lung. `running()` e citit din bucla principala
    inainte de fiecare actiune.
    """

    def __init__(self, key: str = "f12", on_stop: Optional[Callable[[], None]] = None) -> None:
        self.key = key.lower()
        self.on_stop = on_stop
        self._stopped = threading.Event()
        self._paused = threading.Event()
        self._listener = None
        self.reason: str = ""

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    def running(self) -> bool:
        """Predicat pentru `should_continue`: rulam si nu suntem in pauza."""
        return not self._stopped.is_set() and not self._paused.is_set()

    def stop(self, reason: str = "") -> None:
        if not self._stopped.is_set():
            self.reason = reason
            self._stopped.set()
            log.warning("OPRIRE ceruta%s.", f": {reason}" if reason else "")
            if self.on_stop:
                try:
                    self.on_stop()
                except Exception:
                    log.exception("Callback-ul de oprire a esuat.")

    def toggle_pause(self) -> None:
        if self._paused.is_set():
            self._paused.clear()
            print(">> reluat")
        else:
            self._paused.set()
            print(">> in pauza")

    def start(self, pause_key: str = "f11") -> "KillSwitch":
        try:
            from pynput import keyboard
        except Exception:  # pragma: no cover
            log.warning("pynput lipseste: nu exista tasta de oprire de urgenta!")
            return self

        pause_key = pause_key.lower()

        def on_press(key):
            name = None
            if isinstance(key, keyboard.Key):
                name = key.name.lower()
            elif isinstance(key, keyboard.KeyCode) and key.char:
                name = key.char.lower()
            if name == self.key:
                self.stop("oprit de la tastatura")
            elif name == pause_key:
                self.toggle_pause()

        self._listener = keyboard.Listener(on_press=on_press)
        self._listener.daemon = True
        self._listener.start()
        print(f"Oprire de urgenta: {self.key.upper()}   Pauza: {pause_key.upper()}")
        return self

    def close(self) -> None:
        if self._listener is not None:
            self._listener.stop()


class StopFileWatcher:
    """Opreste botul cand apare un fisier anume pe disc.

    Fereastra aplicatiei ruleaza botul ca proces separat si trebuie sa-l poata
    opri. Nu-l omoara: un proces terminat brutal poate ramane cu o tasta
    apasata, iar personajul continua sa alerge in perete dupa ce tu ai inchis
    tot. Asa, botul vede semnalul si iese pe drumul normal, eliberand tastele.
    """

    def __init__(self, path, kill_switch: "KillSwitch", interval: float = 0.4) -> None:
        self.path = Path(path)
        self.kill_switch = kill_switch
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def check(self) -> bool:
        """O singura verificare. Intoarce True daca a cerut oprirea."""
        if self.kill_switch.stopped or not self.path.exists():
            return False
        log.info("Semnal de oprire primit prin %s.", self.path)
        self.kill_switch.stop("oprit din fereastra")
        return True

    def start(self) -> "StopFileWatcher":
        def bucla():
            while not self._stop.wait(self.interval):
                if self.check():
                    return

        self._thread = threading.Thread(target=bucla, daemon=True)
        self._thread.start()
        return self

    def close(self) -> None:
        self._stop.set()


@dataclass
class WatchdogConfig:
    stuck_seconds: float = 90.0  # ecran neschimbat atat timp = blocat
    stuck_diff_threshold: float = 2.0
    max_deaths: int = 3


class Watchdog:
    """Observa daca botul chiar face ceva, sau doar se agita degeaba."""

    def __init__(self, config: Optional[WatchdogConfig] = None) -> None:
        self.config = config or WatchdogConfig()
        self._last_frame: Optional[np.ndarray] = None
        self._last_change_at = time.monotonic()
        self.deaths = 0

    def observe_frame(self, frame: np.ndarray) -> None:
        """Alimenteaza detectorul de blocaj cu cadrul curent."""
        if self._last_frame is None:
            self._last_frame = frame
            return
        if vision.frames_differ(self._last_frame, frame, self.config.stuck_diff_threshold):
            self._last_change_at = time.monotonic()
        self._last_frame = frame

    @property
    def seconds_since_change(self) -> float:
        return time.monotonic() - self._last_change_at

    def is_stuck(self) -> bool:
        return self.seconds_since_change > self.config.stuck_seconds

    def record_death(self) -> None:
        self.deaths += 1
        log.warning("Moarte inregistrata (%d/%d).", self.deaths, self.config.max_deaths)

    def should_abort(self) -> Optional[str]:
        """Motivul pentru care ar trebui sa oprim, sau None daca e in regula."""
        if self.is_stuck():
            return f"ecranul nu s-a schimbat de {self.seconds_since_change:.0f}s (blocat?)"
        if self.deaths >= self.config.max_deaths:
            return f"personajul a murit de {self.deaths} ori"
        return None

    def reset_stuck(self) -> None:
        self._last_change_at = time.monotonic()


@dataclass
class SessionGuard:
    """Limite de sesiune: cat rulam total si cand ne oprim sa respiram."""

    max_runtime_minutes: float = 0.0  # 0 = fara limita
    take_breaks: bool = True
    work_minutes: tuple[float, float] = (25.0, 55.0)
    break_minutes: tuple[float, float] = (2.0, 9.0)

    started_at: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        self._schedule = humanize.break_schedule(self.work_minutes, self.break_minutes)
        self._pending_break = 0.0
        self._next_break_at = 0.0
        self._arm()

    def _arm(self) -> None:
        """Programeaza urmatorul interval de lucru si pauza care-i urmeaza."""
        work, self._pending_break = next(self._schedule)
        self._next_break_at = time.monotonic() + work

    @property
    def elapsed_minutes(self) -> float:
        return (time.monotonic() - self.started_at) / 60.0

    def expired(self) -> bool:
        return self.max_runtime_minutes > 0 and self.elapsed_minutes >= self.max_runtime_minutes

    def break_due(self) -> bool:
        return self.take_breaks and time.monotonic() >= self._next_break_at

    def take_break(self, interruptible: Optional[Callable[[], bool]] = None) -> float:
        """Sta pe loc o pauza. Intoarce cate secunde a stat efectiv."""
        duration = self._pending_break
        print(f"  ~ pauza de {duration/60:.1f} min")
        log.info("Pauza programata: %.0f secunde.", duration)
        deadline = time.monotonic() + duration
        started = time.monotonic()
        while time.monotonic() < deadline:
            if interruptible and not interruptible():
                break
            time.sleep(0.5)
        self._arm()
        return time.monotonic() - started
