"""Captura ecranului.

Singura sursa de informatie a botului. Nu citim memoria jocului si nu ne agatam
de procesul lui: ne uitam la aceiasi pixeli la care te uiti si tu.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

try:  # mss lipseste pe masinile de dezvoltare fara ecran
    import mss

    _HAS_MSS = True
except Exception:  # pragma: no cover - depinde de mediu
    _HAS_MSS = False

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


@dataclass(frozen=True)
class Region:
    """Un dreptunghi in coordonate absolute de ecran."""

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def center(self) -> tuple[int, int]:
        return self.left + self.width // 2, self.top + self.height // 2

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def to_absolute(self, x: int, y: int) -> tuple[int, int]:
        """Converteste coordonate relative la regiune in coordonate de ecran."""
        return self.left + x, self.top + y

    def as_dict(self) -> dict:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: dict) -> "Region":
        return cls(int(data["left"]), int(data["top"]), int(data["width"]), int(data["height"]))

    @classmethod
    def from_points(cls, x1: int, y1: int, x2: int, y2: int) -> "Region":
        left, right = sorted((int(x1), int(x2)))
        top, bottom = sorted((int(y1), int(y2)))
        return cls(left, top, right - left, bottom - top)


class ScreenCapture:
    """Preia cadre de pe ecran, in BGR (formatul cu care lucreaza OpenCV).

    Instanta de mss nu e thread-safe, asa ca o tinem legata de firul care a
    creat obiectul; botul ruleaza oricum captura pe un singur fir.
    """

    def __init__(self, monitor: int = 1) -> None:
        if not _HAS_MSS:
            raise RuntimeError(
                "mss nu e instalat. Ruleaza: pip install -r gamebot/requirements.txt"
            )
        self._sct = mss.mss()
        self._monitor_index = monitor
        self._last_frame: Optional[np.ndarray] = None
        self._last_grab_at: float = 0.0

    @property
    def monitor(self) -> Region:
        m = self._sct.monitors[self._monitor_index]
        return Region(m["left"], m["top"], m["width"], m["height"])

    def grab(self, region: Optional[Region] = None) -> np.ndarray:
        """Un cadru proaspat, ca array BGR."""
        box = region.as_dict() if region else self._sct.monitors[self._monitor_index]
        raw = self._sct.grab(box)
        frame = np.asarray(raw)[:, :, :3]  # BGRA -> BGR, aruncam canalul alfa
        self._last_frame = frame
        self._last_grab_at = time.monotonic()
        return frame

    def grab_cached(self, region: Optional[Region] = None, max_age: float = 0.08) -> np.ndarray:
        """Reutilizeaza ultimul cadru daca e destul de recent.

        Mai multe comportamente se uita la acelasi cadru in aceeasi iteratie
        (viata, tinta, loot). Fara cache-ul asta am face 4-5 capturi inutile
        pe ciclu.
        """
        fresh_enough = (
            self._last_frame is not None
            and region is None
            and (time.monotonic() - self._last_grab_at) < max_age
        )
        if fresh_enough:
            return self._last_frame  # type: ignore[return-value]
        return self.grab(region)

    def save(self, path: str | Path, region: Optional[Region] = None,
             width: Optional[int] = None) -> Path:
        """Salveaza un cadru pe disc, optional micsorat la o latime data."""
        if cv2 is None:
            raise RuntimeError("opencv-python nu e instalat.")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        imagine = self.grab(region)
        if width:
            from . import vision

            imagine = vision.thumbnail(imagine, width)
        cv2.imwrite(str(target), imagine)
        return target

    def close(self) -> None:
        try:
            self._sct.close()
        except Exception:
            pass

    def __enter__(self) -> "ScreenCapture":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class ReplayCapture:
    """Sursa falsa de cadre, dintr-un director cu imagini.

    Serveste la doua lucruri: rulezi logica botului pe Linux fara joc pornit,
    si scrii teste pentru comportamente fara sa ai nevoie de ecran.
    """

    def __init__(self, frames: list[np.ndarray]) -> None:
        if not frames:
            raise ValueError("ReplayCapture are nevoie de cel putin un cadru.")
        self._frames = frames
        self._index = 0

    @classmethod
    def from_directory(cls, directory: str | Path) -> "ReplayCapture":
        if cv2 is None:
            raise RuntimeError("opencv-python nu e instalat.")
        paths = sorted(Path(directory).glob("*.png"))
        frames = [cv2.imread(str(p)) for p in paths]
        return cls([f for f in frames if f is not None])

    @property
    def monitor(self) -> Region:
        h, w = self._frames[0].shape[:2]
        return Region(0, 0, w, h)

    def grab(self, region: Optional[Region] = None) -> np.ndarray:
        frame = self._frames[self._index % len(self._frames)]
        self._index += 1
        if region is None:
            return frame.copy()
        return frame[region.top : region.bottom, region.left : region.right].copy()

    def grab_cached(self, region: Optional[Region] = None, max_age: float = 0.08) -> np.ndarray:
        return self.grab(region)

    def close(self) -> None:
        pass
