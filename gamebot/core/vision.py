"""Interpretarea pixelilor: unde e tinta, cat HP am, ce scrie pe ecran.

Trei tehnici, in ordinea increderii:
  1. template matching  - pentru iconite si elemente de interfata fixe;
  2. masti HSV          - pentru bare de viata si nameplate-uri colorate;
  3. detectie de blob   - pentru noduri de resurse care nu au forma constanta.

Nimic din ce e aici nu atinge procesul jocului.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def _require_cv2() -> None:
    if cv2 is None:
        raise RuntimeError("opencv-python nu e instalat. pip install -r gamebot/requirements.txt")


@dataclass(frozen=True)
class Match:
    """Un rezultat de cautare, in coordonatele imaginii in care s-a cautat."""

    x: int
    y: int
    width: int
    height: int
    score: float

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2

    @property
    def area(self) -> int:
        return self.width * self.height


def find_template(
    haystack: np.ndarray,
    needle: np.ndarray,
    threshold: float = 0.85,
    mask: Optional[np.ndarray] = None,
) -> Optional[Match]:
    """Cea mai buna potrivire a lui `needle` in `haystack`, daca trece pragul.

    Folosim corelatie normalizata, care e tolerabila la variatii de
    luminozitate (util cand jocul are cicluri zi/noapte).
    """
    _require_cv2()
    if haystack is None or needle is None:
        return None
    hh, hw = haystack.shape[:2]
    nh, nw = needle.shape[:2]
    if nh > hh or nw > hw:
        return None

    result = cv2.matchTemplate(haystack, needle, cv2.TM_CCOEFF_NORMED, mask=mask)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if not np.isfinite(max_val) or max_val < threshold:
        return None
    return Match(int(max_loc[0]), int(max_loc[1]), nw, nh, float(max_val))


def find_all_templates(
    haystack: np.ndarray,
    needle: np.ndarray,
    threshold: float = 0.85,
    max_results: int = 20,
) -> list[Match]:
    """Toate apararitiile, fara duplicate suprapuse.

    matchTemplate raporteaza un scor pentru fiecare pixel, deci un singur
    obiect real produce zeci de potriviri vecine. Le comprimam printr-un
    non-maximum suppression simplu, pe distanta.
    """
    _require_cv2()
    hh, hw = haystack.shape[:2]
    nh, nw = needle.shape[:2]
    if nh > hh or nw > hw:
        return []

    result = cv2.matchTemplate(haystack, needle, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(result >= threshold)
    candidates = sorted(
        (Match(int(x), int(y), nw, nh, float(result[y, x])) for x, y in zip(xs, ys)),
        key=lambda m: m.score,
        reverse=True,
    )
    # Un prag prea permisiv pe un fundal uniform poate produce sute de mii de
    # potriviri; dincolo de primele cateva mii, cele bune sunt oricum gasite.
    candidates = candidates[:2000]

    kept: list[Match] = []
    min_gap = max(nw, nh) * 0.6
    for cand in candidates:
        cx, cy = cand.center
        if all(
            np.hypot(cx - k.center[0], cy - k.center[1]) > min_gap for k in kept
        ):
            kept.append(cand)
        if len(kept) >= max_results:
            break
    return kept


def hsv_mask(image: np.ndarray, low: Iterable[int], high: Iterable[int]) -> np.ndarray:
    """Masca binara pentru pixelii dintr-un interval HSV.

    HSV separa culoarea de luminozitate, deci o bara rosie ramane detectabila
    si cand efectele grafice o intuneca. In OpenCV H merge 0-179, nu 0-359.
    """
    _require_cv2()
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, np.array(list(low), dtype=np.uint8), np.array(list(high), dtype=np.uint8))


def bar_fill_ratio(
    image: np.ndarray,
    low: Iterable[int],
    high: Iterable[int],
    axis: str = "horizontal",
) -> float:
    """Cat la suta e plina o bara (viata, mana, cast bar).

    Nu numaram pur si simplu pixelii colorati, fiindca marginile si textul
    suprapus falsifica raportul. Ne uitam la cea mai din dreapta coloana
    (respectiv cel mai de sus rand) care mai are culoare si raportam pozitia
    ei la latimea barei. Asta rezista si cand bara are gradient sau striatii.
    """
    if image is None or image.size == 0:
        return 0.0
    mask = hsv_mask(image, low, high)
    if not mask.any():
        return 0.0

    if axis == "horizontal":
        # O coloana conteaza doar daca e colorata pe o buna parte din inaltime,
        # altfel un pixel razlet de UI ar da bara plina.
        column_hits = (mask > 0).sum(axis=0)
        threshold = max(1, int(mask.shape[0] * 0.3))
        filled = np.where(column_hits >= threshold)[0]
        if filled.size == 0:
            return 0.0
        return float((filled.max() + 1) / mask.shape[1])

    row_hits = (mask > 0).sum(axis=1)
    threshold = max(1, int(mask.shape[1] * 0.3))
    filled = np.where(row_hits >= threshold)[0]
    if filled.size == 0:
        return 0.0
    return float((filled.max() + 1) / mask.shape[0])


def color_blobs(
    image: np.ndarray,
    low: Iterable[int],
    high: Iterable[int],
    min_area: int = 60,
    max_results: int = 15,
) -> list[Match]:
    """Grupuri conexe de pixeli dintr-un interval de culoare.

    Asa gasim nameplate-uri de mob (culoare fixa deasupra capului) sau noduri
    de resurse care sclipesc. Inchiderea morfologica lipeste literele unui
    nume intr-un singur bloc, in loc sa raporteze fiecare caracter separat.
    """
    _require_cv2()
    mask = hsv_mask(image, low, high)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    count, _, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    blobs: list[Match] = []
    for i in range(1, count):  # eticheta 0 e fundalul
        x, y, w, h, area = stats[i]
        if area < min_area:
            continue
        blobs.append(Match(int(x), int(y), int(w), int(h), float(area)))

    blobs.sort(key=lambda m: m.score, reverse=True)
    return blobs[:max_results]


def thumbnail(image: np.ndarray, width: int = 240) -> np.ndarray:
    """Micsoreaza o imagine pastrand proportiile.

    Ancorele de traseu se compara intre ele, nu se privesc: la 240 px latime
    raman toate detaliile care conteaza (forma terenului, asezarea cladirilor),
    dar fisierele sunt mici si comparatia e de zeci de ori mai rapida. Tot
    micsorarea sterge si detaliile care ne incurcau - un jucator care trece
    prin cadru devine cateva puncte, nu o diferenta care strica potrivirea.
    """
    _require_cv2()
    if image is None or image.size == 0:
        return image
    h, w = image.shape[:2]
    if w <= width:
        return image
    inaltime = max(1, int(round(h * width / w)))
    return cv2.resize(image, (width, inaltime), interpolation=cv2.INTER_AREA)


def frames_differ(a: np.ndarray, b: np.ndarray, threshold: float = 2.0) -> bool:
    """Spune daca doua cadre difera vizibil.

    Folosit de watchdog: daca ecranul e identic minute intregi, personajul e
    blocat intr-un colt de gard si nu are rost sa continue.
    """
    if a is None or b is None or a.shape != b.shape:
        return True
    return float(np.mean(cv2.absdiff(a, b))) > threshold


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Scor 0..1 intre doua imagini de aceeasi marime (corelatie normalizata)."""
    _require_cv2()
    if a is None or b is None:
        return 0.0
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    result = cv2.matchTemplate(a, b, cv2.TM_CCOEFF_NORMED)
    value = float(result.max())
    return value if np.isfinite(value) else 0.0


class TemplateLibrary:
    """Incarca si tine in memorie imaginile de referinta din `templates/`.

    Numele fisierului e cheia: `templates/loot_bag.png` -> `lib["loot_bag"]`.
    Incarcarea e lenesa, ca sa nu tinem in RAM sabloane pe care profilul
    curent nu le foloseste.
    """

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self._cache: dict[str, Optional[np.ndarray]] = {}

    def get(self, name: str) -> Optional[np.ndarray]:
        if name not in self._cache:
            _require_cv2()
            path = self.directory / f"{name}.png"
            self._cache[name] = cv2.imread(str(path)) if path.exists() else None
        return self._cache[name]

    def __getitem__(self, name: str) -> np.ndarray:
        image = self.get(name)
        if image is None:
            raise KeyError(
                f"Lipseste sablonul '{name}'. Creeaza-l cu: python -m gamebot.main calibrate"
            )
        return image

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    def available(self) -> list[str]:
        return sorted(p.stem for p in self.directory.glob("*.png"))
