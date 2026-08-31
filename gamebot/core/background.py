"""Rulare in fundal: captura si input trimise direct catre fereastra jocului.

Modul normal se uita la ecran si misca mouse-ul real, deci calculatorul e
ocupat cat ruleaza botul. Modul asta incearca sa ocoleasca amandoua limitele:

  WindowCapture   - cere ferestrei sa se deseneze intr-o imagine, cu PrintWindow,
                    in loc sa fotografieze ecranul. Merge si cand fereastra e
                    acoperita de alte ferestre.
  PostMessageBackend - trimite tastele si clicurile ca mesaje direct catre
                    fereastra jocului, fara sa atinga mouse-ul real.

ATENTIE, si asta nu e o formalitate: **niciuna dintre cele doua nu e garantata**.
Functioneaza pe aplicatiile care deseneaza obisnuit si care isi citesc input-ul
din coada de mesaje. Multe jocuri 3D nu fac nici una, nici alta: deseneaza
direct prin DirectX (si atunci PrintWindow intoarce o imagine neagra) si isi
citesc input-ul prin DirectInput sau Raw Input, care ocolesc complet mesajele
trimise de noi.

De aceea exista `diagnostic()`: iti spune in cateva secunde daca merge pe jocul
tau, in loc sa te lase sa descoperi dupa o ora ca botul apasa in gol.
"""

from __future__ import annotations

import ctypes
import logging
import platform
import time
from ctypes import wintypes
from typing import Optional

import numpy as np

from .capture import Region

log = logging.getLogger(__name__)

# Mesajele Windows de care avem nevoie.
WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x0100, 0x0101, 0x0102
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MOUSEWHEEL = 0x020A
MK_LBUTTON, MK_RBUTTON = 0x0001, 0x0002

PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002


def _windows_only() -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Modul de fundal exista doar pe Windows.")


# --------------------------------------------------------------------- taste

_TASTE_SPECIALE = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B,
    "escape": 0x1B, "backspace": 0x08, "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
}


def vk_code(nume: str) -> Optional[int]:
    """Codul virtual al unei taste, dupa numele folosit in profil."""
    if not nume:
        return None
    nume = nume.lower()
    if nume in _TASTE_SPECIALE:
        return _TASTE_SPECIALE[nume]
    if len(nume) == 1:
        return ord(nume.upper())
    if nume.startswith("f") and nume[1:].isdigit():
        numar = int(nume[1:])
        if 1 <= numar <= 24:
            return 0x70 + numar - 1  # VK_F1 e 0x70
    return None


# ------------------------------------------------------------------ captura


class WindowCapture:
    """Captureaza o fereastra anume, chiar daca e acoperita de altele.

    Aceeasi interfata ca `ScreenCapture`, ca sa poata fi pusa in locul ei fara
    ca restul codului sa stie diferenta.
    """

    def __init__(self, hwnd: int) -> None:
        _windows_only()
        self.hwnd = hwnd
        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32
        self._last: Optional[np.ndarray] = None

    @property
    def monitor(self) -> Region:
        rect = wintypes.RECT()
        self._user32.GetClientRect(self.hwnd, ctypes.byref(rect))
        punct = wintypes.POINT(0, 0)
        self._user32.ClientToScreen(self.hwnd, ctypes.byref(punct))
        return Region(punct.x, punct.y, rect.right - rect.left, rect.bottom - rect.top)

    def grab(self, region: Optional[Region] = None) -> np.ndarray:
        """Un cadru cu aria de client a ferestrei, in BGR."""
        client = self.monitor
        latime, inaltime = max(1, client.width), max(1, client.height)

        hdc_fereastra = self._user32.GetDC(self.hwnd)
        hdc_mem = self._gdi32.CreateCompatibleDC(hdc_fereastra)
        bitmap = self._gdi32.CreateCompatibleBitmap(hdc_fereastra, latime, inaltime)
        vechi = self._gdi32.SelectObject(hdc_mem, bitmap)

        try:
            self._user32.PrintWindow(self.hwnd, hdc_mem, PW_CLIENTONLY | PW_RENDERFULLCONTENT)

            # Antet pentru o imagine pe 32 de biti, cu randurile in ordinea de sus
            # in jos (de aici inaltimea negativa).
            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD),
                ]

            antet = BITMAPINFOHEADER()
            antet.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            antet.biWidth = latime
            antet.biHeight = -inaltime
            antet.biPlanes = 1
            antet.biBitCount = 32
            antet.biCompression = 0

            buffer = ctypes.create_string_buffer(latime * inaltime * 4)
            self._gdi32.GetDIBits(hdc_mem, bitmap, 0, inaltime, buffer,
                                  ctypes.byref(antet), 0)

            cadru = np.frombuffer(buffer, dtype=np.uint8).reshape((inaltime, latime, 4))[:, :, :3]
            cadru = np.ascontiguousarray(cadru)
        finally:
            self._gdi32.SelectObject(hdc_mem, vechi)
            self._gdi32.DeleteObject(bitmap)
            self._gdi32.DeleteDC(hdc_mem)
            self._user32.ReleaseDC(self.hwnd, hdc_fereastra)

        self._last = cadru
        if region is None:
            return cadru

        # Regiunile vin in coordonate de ecran; le mutam in coordonatele ferestrei.
        x = region.left - client.left
        y = region.top - client.top
        return cadru[max(0, y):y + region.height, max(0, x):x + region.width]

    def grab_cached(self, region: Optional[Region] = None, max_age: float = 0.08) -> np.ndarray:
        return self.grab(region)

    def save(self, path, region: Optional[Region] = None, width: Optional[int] = None):
        from pathlib import Path

        import cv2

        from . import vision

        imagine = self.grab(region)
        if width:
            imagine = vision.thumbnail(imagine, width)
        tinta = Path(path)
        tinta.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(tinta), imagine)
        return tinta

    def close(self) -> None:
        pass


# -------------------------------------------------------------------- input


class PostMessageBackend:
    """Trimite input direct catre fereastra, fara sa atinga mouse-ul real.

    Implementeaza aceeasi interfata ca backend-ul obisnuit, deci
    `InputController` il poate folosi fara sa stie ca e altceva.
    """

    def __init__(self, hwnd: int) -> None:
        _windows_only()
        self.hwnd = hwnd
        self._user32 = ctypes.windll.user32
        self._pozitie = (0, 0)
        self.name = "postmessage"

    def _lparam_pozitie(self, x: int, y: int) -> int:
        return (y << 16) | (x & 0xFFFF)

    def _client(self, x: int, y: int) -> tuple[int, int]:
        """Din coordonate de ecran in coordonate ale ferestrei."""
        punct = wintypes.POINT(int(x), int(y))
        self._user32.ScreenToClient(self.hwnd, ctypes.byref(punct))
        return punct.x, punct.y

    def move_to(self, x: int, y: int) -> None:
        self._pozitie = (int(x), int(y))
        cx, cy = self._client(x, y)
        self._user32.PostMessageW(self.hwnd, WM_MOUSEMOVE, 0, self._lparam_pozitie(cx, cy))

    def mouse_down(self, button: str) -> None:
        cx, cy = self._client(*self._pozitie)
        mesaj = WM_RBUTTONDOWN if button == "right" else WM_LBUTTONDOWN
        flag = MK_RBUTTON if button == "right" else MK_LBUTTON
        self._user32.PostMessageW(self.hwnd, mesaj, flag, self._lparam_pozitie(cx, cy))

    def mouse_up(self, button: str) -> None:
        cx, cy = self._client(*self._pozitie)
        mesaj = WM_RBUTTONUP if button == "right" else WM_LBUTTONUP
        self._user32.PostMessageW(self.hwnd, mesaj, 0, self._lparam_pozitie(cx, cy))

    def key_down(self, key: str) -> None:
        vk = vk_code(key)
        if vk is None:
            log.debug("Tasta '%s' nu are cod virtual cunoscut.", key)
            return
        self._user32.PostMessageW(self.hwnd, WM_KEYDOWN, vk, 0)

    def key_up(self, key: str) -> None:
        vk = vk_code(key)
        if vk is None:
            return
        self._user32.PostMessageW(self.hwnd, WM_KEYUP, vk, 0)

    def scroll(self, clicks: int) -> None:
        cx, cy = self._client(*self._pozitie)
        self._user32.PostMessageW(self.hwnd, WM_MOUSEWHEEL,
                                  (clicks * 120) << 16, self._lparam_pozitie(cx, cy))

    def position(self) -> tuple[int, int]:
        return self._pozitie


# --------------------------------------------------------------- diagnostic


def diagnostic(hwnd: int, titlu: str = "") -> dict:
    """Verifica daca modul de fundal chiar merge pe jocul asta.

    Captura o putem verifica singuri: daca imaginea intoarsa e complet neagra,
    fereastra deseneaza prin DirectX si PrintWindow nu are ce citi.

    Input-ul NU poate fi verificat automat - ar insemna sa ghicim ce se schimba
    in joc dupa o apasare. De aceea intoarcem doar verdictul pentru captura, iar
    pentru input spunem clar ca ramane de incercat pe viu.
    """
    rezultat = {"captura": False, "detaliu": "", "latime": 0, "inaltime": 0}
    try:
        captura = WindowCapture(hwnd)
        cadru = captura.grab()
        rezultat["latime"] = int(cadru.shape[1])
        rezultat["inaltime"] = int(cadru.shape[0])

        medie = float(cadru.mean())
        if medie < 2.0:
            rezultat["detaliu"] = ("imaginea e complet neagra: fereastra deseneaza "
                                   "prin DirectX si nu poate fi citita in fundal")
        else:
            # Un al doilea cadru, ca sa vedem daca chiar se actualizeaza.
            time.sleep(0.6)
            al_doilea = captura.grab()
            difera = float(np.mean(np.abs(cadru.astype(int) - al_doilea.astype(int))))
            rezultat["captura"] = True
            rezultat["detaliu"] = (f"imagine valida (luminozitate medie {medie:.0f}, "
                                   f"schimbare intre cadre {difera:.1f})")
    except Exception as exc:
        rezultat["detaliu"] = f"captura a esuat: {exc}"

    return rezultat
