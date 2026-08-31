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
from ..core.pickup import Blacklist, acoperire, culori_din_profil, find_loot
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
        self.nume_culori = list(loot.get("colors") or [])
        self.culori = culori_din_profil(profile, self.nume_culori)
        self.diagnostic = bool(section.get("diagnostic", True))
        self.sample_key = str(section.get("sample_key", "f8")).lower()

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

            # Raportam ce a gasit fiecare culoare INAINTE de filtrul de raza.
            # "Nu functioneaza" poate insemna trei lucruri complet diferite:
            # fereastra gresita, culori care nu se potrivesc, sau raza prea
            # mica. Randul asta le deosebeste dintr-o privire.
            if runner.diagnostic:
                pe_culoare = []
                for nume, (low, high) in zip(runner.nume_culori, runner.culori):
                    toate = find_loot(cadru, [(low, high)], centru_local,
                                      min_area=runner.min_area)
                    pe_culoare.append(f"{nume}:{len(toate)}")
                runner.spune(f"  [{zona.width}x{zona.height} @ {zona.left},{zona.top}] "
                             f"raza {runner.radius} | " + "  ".join(pe_culoare)
                             + f" | in raza: {len(obiecte)}")

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


def _citeste_culoarea_de_sub_cursor(runner: PickupRunner) -> None:
    """Spune ce culoare e sub mouse, gata de pus in profil.

    Asta inlocuieste ghicitul. Pui cursorul pe eticheta unui obiect cazut,
    apesi tasta, si primesti intervalul HSV care o acopera - masurat pe ecranul
    tau, nu presupus de altcineva.
    """
    try:
        import cv2
        import numpy as np
        import pyautogui

        from ..core.capture import Region, ScreenCapture

        x, y = pyautogui.position()
        # Un patrat mic in jurul cursorului: un singur pixel ar prinde exact
        # marginea antialiasata a unei litere si ar da o culoare inventata.
        zona = Region(int(x) - 4, int(y) - 4, 9, 9)
        with ScreenCapture(runner.profile.monitor) as captura:
            bucata = captura.grab(zona)

        hsv = cv2.cvtColor(bucata, cv2.COLOR_BGR2HSV).reshape(-1, 3)
        median = np.median(hsv, axis=0).astype(int)
        low = np.clip(median - np.array([8, 60, 60]), [0, 0, 0], [179, 255, 255])
        high = np.clip(median + np.array([8, 40, 40]), [0, 0, 0], [179, 255, 255])

        runner.spune(f"\nCuloare la ({x}, {y}): HSV median {tuple(median)}")

        # Verificam proba pe tot ecranul jocului inainte sa o dam mai departe.
        fereastra = find_window(runner.profile.window_title)
        zona = fereastra.region if fereastra else None
        with ScreenCapture(runner.profile.monitor) as captura:
            intreg = captura.grab(zona)
        procent = acoperire(intreg, low, high) * 100

        if procent > 5.0:
            runner.spune(f"  ATENTIE: intervalul asta prinde {procent:.0f}% din ecran.")
            runner.spune("  Ai nimerit langa obiect, nu pe el. Pune cursorul fix pe")
            runner.spune("  mijlocul etichetei colorate si incearca din nou.\n")
            return

        runner.spune(f"  (prinde {procent:.2f}% din ecran - bine)")
        runner.spune("  De pus in profil, sub `colors:`")
        runner.spune(f"    low: [{low[0]}, {low[1]}, {low[2]}]")
        runner.spune(f"    high: [{high[0]}, {high[1]}, {high[2]}]\n")
    except Exception as exc:
        runner.spune(f"Nu am putut citi culoarea: {exc}")


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
        elif nume == runner.sample_key:
            _citeste_culoarea_de_sub_cursor(runner)
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
        print(f"Poti totusi porni si folosi {runner.sample_key.upper()} ca sa masori")
        print("culorile de la tine, apoi le pui in profil.\n")

    print("=" * 62)
    print(f"  {runner.hotkey.upper()}  porneste / opreste culesul (apare cercul)")
    print(f"  {runner.sample_key.upper()}  citeste culoarea de sub cursor")
    print("  F12 inchide")
    print("=" * 62)
    print(f"Raza cercului: {runner.radius} px   Culori cautate: "
          f"{', '.join(runner.nume_culori) or 'niciuna'}")
    print("\nDaca nu aduna nimic: pune cursorul pe eticheta unui obiect cazut")
    print(f"si apasa {runner.sample_key.upper()}. Culoarea masurata apare aici.\n", flush=True)

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
