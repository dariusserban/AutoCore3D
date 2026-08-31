"""Cercul desenat peste joc.

Nu e desenat *in* joc: e o fereastra proprie, transparenta, care sta deasupra
tuturor. Jocul nu stie ca exista si nu e atins in niciun fel - la fel cum o
fereastra oarecare poate sta peste el.

Doua lucruri fac fereastra asta sa nu deranjeze:

  culoare-cheie  - fundalul e desenat intr-o culoare care devine complet
                   transparenta, deci se vede doar conturul cercului;
  click-through  - stilul WS_EX_TRANSPARENT face ca toate clicurile sa treaca
                   prin ea catre joc. Fara el, fereastra ar inghiti exact
                   clicurile pe care le trimitem ca sa ridicam obiectele, si
                   nimic n-ar functiona.
"""

from __future__ import annotations

import logging
import platform

try:
    import tkinter as tk
except Exception:  # pragma: no cover
    tk = None

log = logging.getLogger(__name__)

# Culoarea care devine transparenta. Un verde imposibil de confundat cu ceva
# desenat de noi, ca sa nu gaurim din greseala conturul cercului.
CULOARE_CHEIE = "#010203"

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000


class CircleOverlay:
    """Un cerc care urmareste centrul ferestrei jocului."""

    def __init__(self, root, radius: int = 200, culoare: str = "#3fd977",
                 grosime: int = 3) -> None:
        if tk is None:  # pragma: no cover
            raise RuntimeError("tkinter lipseste; cercul nu poate fi desenat.")

        self.radius = radius
        self.culoare = culoare
        self.grosime = grosime
        self._vizibil = False

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", CULOARE_CHEIE)
        except tk.TclError:
            # Pe alte sisteme decat Windows nu exista culoare-cheie; ramane un
            # dreptunghi semi-transparent, mai putin frumos dar utilizabil.
            self.win.attributes("-alpha", 0.35)

        self.canvas = tk.Canvas(self.win, bg=CULOARE_CHEIE, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.win.withdraw()

        self._fa_click_through()

    def _fa_click_through(self) -> None:
        """Lasa clicurile sa treaca prin fereastra catre joc."""
        if platform.system() != "Windows":
            return
        try:
            import ctypes

            self.win.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
            stiluri = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                stiluri | WS_EX_LAYERED | WS_EX_TRANSPARENT
                | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            )
        except Exception as exc:  # pragma: no cover
            log.warning("Nu am putut face cercul transparent la clicuri: %s", exc)

    # ------------------------------------------------------------- desenare

    def _deseneaza(self) -> None:
        latura = self.radius * 2 + self.grosime * 2 + 4
        self.canvas.delete("all")
        self.canvas.configure(width=latura, height=latura)

        centru = latura // 2
        r = self.radius
        self.canvas.create_oval(
            centru - r, centru - r, centru + r, centru + r,
            outline=self.culoare, width=self.grosime,
        )
        # O cruce mica in centru, ca sa se vada pe cine e centrat cercul.
        self.canvas.create_line(centru - 7, centru, centru + 7, centru,
                                fill=self.culoare, width=1)
        self.canvas.create_line(centru, centru - 7, centru, centru + 7,
                                fill=self.culoare, width=1)

    def show(self, center: tuple[int, int]) -> None:
        """Afiseaza cercul centrat pe punctul dat, in coordonate de ecran."""
        self._deseneaza()
        latura = self.radius * 2 + self.grosime * 2 + 4
        x = int(center[0] - latura // 2)
        y = int(center[1] - latura // 2)
        self.win.geometry(f"{latura}x{latura}+{x}+{y}")
        if not self._vizibil:
            self.win.deiconify()
            self.win.attributes("-topmost", True)
            self._vizibil = True

    def hide(self) -> None:
        if self._vizibil:
            self.win.withdraw()
            self._vizibil = False

    def set_radius(self, radius: int) -> None:
        self.radius = max(20, int(radius))

    def set_culoare(self, culoare: str) -> None:
        self.culoare = culoare

    @property
    def vizibil(self) -> bool:
        return self._vizibil

    def destroy(self) -> None:
        try:
            self.win.destroy()
        except Exception:
            pass
