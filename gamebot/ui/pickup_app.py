"""Culesul cu tasta: apesi, apare cercul, se aduna tot ce e inauntru.

Cum e impartita treaba pe fire, si de ce:

  firul principal - bucla Tk, care deseneaza cercul. Tk nu suporta sa fie atins
                    din alt fir, deci desenarea sta aici si atat.
  firul de lucru  - captura si clicurile. Fiecare click are pauzele lui; daca
                    ar rula pe firul Tk, cercul ar ingheta cat timp se aduna.
  firul pynput    - asculta tasta si comuta un steag.

Firul de lucru isi face propria captura: `mss` nu se poate imparti intre fire.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
from pathlib import Path

try:
    import tkinter as tk
except Exception:  # pragma: no cover
    raise SystemExit("Nu gasesc tkinter; cercul nu poate fi desenat.")

from ..core.capture import ScreenCapture
from ..core.config import Profile
from ..core.input_ctl import InputController
from ..core.pickup import Blacklist, culori_din_profil, find_loot
from ..core.window import find_window
from .overlay import CircleOverlay


class PickupRunner:
    """Starea comuna intre fire. Steaguri simple, fara nimic de blocat."""

    def __init__(self, profile: Profile) -> None:
        self.profile = profile
        section = profile.section("pickup")
        self.hotkey = str(section.get("hotkey", "f7")).lower()
        self.radius = int(section.get("radius", 260))
        self.interval = float(section.get("interval", 0.7))
        self.max_per_pass = int(section.get("max_per_pass", 6))
        self.click_offset_y = int(section.get("click_offset_y", 12))

        loot = profile.section("loot")
        self.min_area = int(section.get("min_area", loot.get("min_area", 25)))
        self.culori = culori_din_profil(profile, loot.get("colors") or [])

        self.activ = threading.Event()
        self.oprit = threading.Event()
        self.centru = (0, 0)
        self.mesaje: queue.Queue[str] = queue.Queue()
        self.adunate = 0

    def spune(self, text: str) -> None:
        self.mesaje.put(text)

    def comuta(self) -> None:
        if self.activ.is_set():
            self.activ.clear()
            self.spune(f"Cules OPRIT. Total adunate: {self.adunate}")
        else:
            self.activ.set()
            self.spune(f"Cules PORNIT (raza {self.radius} px)")


def _bucla_de_lucru(runner: PickupRunner) -> None:
    """Captureaza, cauta obiecte in cerc si da click pe ele."""
    capture = ScreenCapture(runner.profile.monitor)
    controller = InputController()
    blacklist = Blacklist(seconds=float(runner.profile.section("pickup").get(
        "blacklist_seconds", 12.0)))

    fereastra = None
    ultima_cautare = 0.0

    try:
        while not runner.oprit.is_set():
            if not runner.activ.is_set():
                blacklist.clear()
                time.sleep(0.08)
                continue

            # Fereastra se cauta rar: se muta greu, iar cautarea nu e gratis.
            if fereastra is None or time.monotonic() - ultima_cautare > 5.0:
                fereastra = find_window(runner.profile.window_title)
                ultima_cautare = time.monotonic()

            zona = fereastra.region if fereastra else capture.monitor
            runner.centru = zona.center

            try:
                cadru = capture.grab(zona)
            except Exception as exc:
                runner.spune(f"Captura a esuat: {exc}")
                time.sleep(0.5)
                continue

            # Personajul e in centrul ferestrei; cautam in jurul lui.
            centru_local = (zona.width // 2, zona.height // 2)
            obiecte = find_loot(
                cadru, runner.culori, centru_local,
                radius=runner.radius, min_area=runner.min_area,
                blacklist=blacklist, offset=(zona.left, zona.top),
            )

            for blob in obiecte[:runner.max_per_pass]:
                if not runner.activ.is_set() or runner.oprit.is_set():
                    break
                x, y = blob.center
                controller.quick_click(x, y + runner.click_offset_y)
                blacklist.add(x, y)
                runner.adunate += 1
                time.sleep(0.12)

            if obiecte:
                runner.spune(f"  am incercat {min(len(obiecte), runner.max_per_pass)} "
                             f"obiect(e) (total {runner.adunate})")

            time.sleep(runner.interval)
    finally:
        try:
            controller.release_all()
        except Exception:
            pass
        capture.close()


def _asculta_tasta(runner: PickupRunner) -> None:
    from pynput import keyboard

    def la_apasare(key):
        nume = None
        if isinstance(key, keyboard.Key):
            nume = key.name.lower()
        elif isinstance(key, keyboard.KeyCode) and key.char:
            nume = key.char.lower()

        if nume == runner.hotkey:
            runner.comuta()
        elif nume == "f12":
            runner.spune("Inchid culesul.")
            runner.activ.clear()
            runner.oprit.set()

    ascultator = keyboard.Listener(on_press=la_apasare)
    ascultator.daemon = True
    ascultator.start()


def porneste(profile_path: str | Path) -> int:
    profile = Profile.load(profile_path)
    runner = PickupRunner(profile)

    if not runner.culori:
        print("Profilul nu are culori de obiect definite (loot.colors).")
        print("Fara ele nu am ce cauta pe jos.")
        return 1

    print(f"Cules cu tasta {runner.hotkey.upper()}  |  F12 inchide")
    print(f"Raza cercului: {runner.radius} px (loot.pickup_radius / pickup.radius)")
    print("Apasa tasta in joc: apare cercul si se aduna tot ce e inauntru.\n", flush=True)

    root = tk.Tk()
    root.withdraw()
    overlay = CircleOverlay(root, radius=runner.radius,
                            culoare=str(profile.section("pickup").get("culoare", "#3fd977")))

    _asculta_tasta(runner)
    lucrator = threading.Thread(target=_bucla_de_lucru, args=(runner,), daemon=True)
    lucrator.start()

    def pompeaza():
        """Singurul loc din care se atinge Tk."""
        while True:
            try:
                print(runner.mesaje.get_nowait(), flush=True)
            except queue.Empty:
                break

        if runner.oprit.is_set():
            overlay.destroy()
            root.quit()
            return

        if runner.activ.is_set():
            overlay.show(runner.centru)
        else:
            overlay.hide()

        root.after(80, pompeaza)

    root.after(80, pompeaza)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        runner.oprit.set()

    print(f"\nGata. Obiecte incercate in sesiunea asta: {runner.adunate}")
    return 0
