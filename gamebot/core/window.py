"""Gasirea ferestrei jocului si masurarea ei.

De ce conteaza: daca stim unde e fereastra si cat e de mare, putem exprima
regiunile de interfata ca procente din ea - "minimapa e in coltul din dreapta
sus, ocupa 16% din latime" - in loc de coordonate fixe in pixeli. Asa profilul
merge la orice rezolutie si pe orice monitor, fara ca nimeni sa traga
dreptunghiuri cu mouse-ul.

Masuram *aria de client*, nu fereastra intreaga. Bara de titlu si chenarul au
grosimi diferite de la o tema Windows la alta; daca le-am include, toate
procentele s-ar decala cu cativa pixeli in jos si la dreapta, iar barele de
viata ar fi citite pe langa.
"""

from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from typing import Optional

from .capture import Region

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WindowInfo:
    """Aria de client a unei ferestre, in coordonate de ecran."""

    title: str
    region: Region

    @property
    def is_reasonable(self) -> bool:
        """O fereastra de joc are o marime plauzibila.

        Filtreaza ferestrele ascunse sau minimizate, care raporteaza dimensiuni
        de cateva zeci de pixeli sau chiar zero.
        """
        return self.region.width >= 640 and self.region.height >= 400


def _find_windows_ctypes(fragment: str) -> list[WindowInfo]:
    """Enumereaza ferestrele vizibile al caror titlu contine `fragment`.

    Folosim direct API-ul Windows prin ctypes, ca sa nu adaugam o dependenta
    doar pentru atat si ca sa putem lua aria de client exacta.
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gasite: list[WindowInfo] = []
    cautat = fragment.lower()

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        lungime = user32.GetWindowTextLengthW(hwnd)
        if lungime == 0:
            return True
        buf = ctypes.create_unicode_buffer(lungime + 1)
        user32.GetWindowTextW(hwnd, buf, lungime + 1)
        titlu = buf.value
        if cautat not in titlu.lower():
            return True

        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return True
        punct = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(punct)):
            return True

        gasite.append(WindowInfo(
            title=titlu,
            region=Region(punct.x, punct.y, rect.right - rect.left, rect.bottom - rect.top),
        ))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return gasite


def _find_windows_pygetwindow(fragment: str) -> list[WindowInfo]:
    """Rezerva, daca apelul direct nu merge. Include si chenarul ferestrei."""
    try:
        import pygetwindow
    except Exception:
        return []
    gasite = []
    for w in pygetwindow.getAllWindows():
        titlu = getattr(w, "title", "") or ""
        if fragment.lower() in titlu.lower():
            try:
                gasite.append(WindowInfo(titlu, Region(w.left, w.top, w.width, w.height)))
            except Exception:
                continue
    return gasite


def find_window(fragment: str) -> Optional[WindowInfo]:
    """Prima fereastra cu titlul potrivit si cu marime plauzibila."""
    if not fragment:
        return None
    if platform.system() != "Windows":
        return None

    candidate: list[WindowInfo] = []
    try:
        candidate = _find_windows_ctypes(fragment)
    except Exception as exc:
        log.debug("Enumerarea directa a ferestrelor a esuat: %s", exc)
    if not candidate:
        candidate = _find_windows_pygetwindow(fragment)

    bune = [w for w in candidate if w.is_reasonable]
    if not bune:
        if candidate:
            log.info("Am gasit fereastra '%s', dar pare minimizata.", candidate[0].title)
        return None

    # Daca sunt mai multe (un client si un launcher, de exemplu), o luam pe cea
    # mai mare - jocul propriu-zis.
    bune.sort(key=lambda w: w.region.width * w.region.height, reverse=True)
    ales = bune[0]
    log.info("Fereastra jocului: '%s' %dx%d la (%d, %d)", ales.title,
             ales.region.width, ales.region.height, ales.region.left, ales.region.top)
    return ales


def relative_region(window: Region, rel: tuple[float, float, float, float]) -> Region:
    """Converteste (x, y, latime, inaltime) in procente la pixeli absoluti.

    Valorile sunt fractii din aria de client: (0.83, 0.03, 0.16, 0.28) inseamna
    "incepe la 83% din latime si 3% din inaltime, ocupa 16% pe orizontala".
    """
    x, y, w, h = rel
    return Region(
        left=window.left + int(round(window.width * x)),
        top=window.top + int(round(window.height * y)),
        width=max(1, int(round(window.width * w))),
        height=max(1, int(round(window.height * h))),
    )
