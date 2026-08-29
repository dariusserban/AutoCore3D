"""Calibrare: transforma ce vezi pe ecran in valori pentru profil.

Trei operatii, toate pornind de la o captura a ecranului:

  region   - selectezi cu mouse-ul un dreptunghi (bara de viata, minimapa) si
             primesti bucata de YAML gata de lipit in profil;
  template - selectezi un element (iconita, buton) si il salveaza ca PNG in
             `templates/`, ca botul sa-l poata cauta;
  color    - selectezi o zona colorata si iti da intervalul HSV care o acopera.

Ruleaza-le cu jocul deschis, in fereastra, pe rezolutia la care vei juca.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import numpy as np

from ..core.capture import Region, ScreenCapture

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def _require_gui() -> None:
    if cv2 is None:
        raise RuntimeError("opencv-python nu e instalat.")


def _grab_after_countdown(monitor: int, delay: int = 4) -> np.ndarray:
    """Numara invers, ca sa apuci sa dai alt-tab in joc inainte de captura."""
    print(f"Comut pe joc si fac captura in {delay} secunde...")
    for remaining in range(delay, 0, -1):
        print(f"  {remaining}...", end="\r", flush=True)
        time.sleep(1)
    print("  captura facuta.      ")
    with ScreenCapture(monitor) as capture:
        return capture.grab()


def _select(frame: np.ndarray, prompt: str) -> Optional[Region]:
    """Deschide o fereastra si lasa utilizatorul sa traga un dreptunghi."""
    _require_gui()
    print(f"\n{prompt}")
    print("Trage un dreptunghi cu mouse-ul, apoi ENTER. ESC anuleaza.")

    # Micsoram pentru afisare daca ecranul e mai mare decat fereastra utila,
    # dar raportam coordonatele inapoi la scara reala.
    h, w = frame.shape[:2]
    scale = min(1.0, 1600 / w, 900 / h)
    shown = cv2.resize(frame, (int(w * scale), int(h * scale))) if scale < 1.0 else frame

    box = cv2.selectROI("calibrare - trage un dreptunghi", shown, showCrosshair=True)
    cv2.destroyAllWindows()

    x, y, bw, bh = box
    if bw == 0 or bh == 0:
        print("Selectie anulata.")
        return None
    return Region(int(x / scale), int(y / scale), int(bw / scale), int(bh / scale))


def calibrate_region(name: str, monitor: int = 1) -> Optional[Region]:
    """Selecteaza o regiune si tipareste YAML-ul pentru profil."""
    frame = _grab_after_countdown(monitor)
    region = _select(frame, f"Selecteaza regiunea '{name}'")
    if region is None:
        return None

    print("\nAdauga in profil, sub `regions:`\n")
    print(f"  {name}:")
    print(f"    left: {region.left}")
    print(f"    top: {region.top}")
    print(f"    width: {region.width}")
    print(f"    height: {region.height}\n")
    return region


def calibrate_template(name: str, templates_dir: str | Path, monitor: int = 1) -> Optional[Path]:
    """Decupeaza un element de interfata si il salveaza ca sablon."""
    frame = _grab_after_countdown(monitor)
    region = _select(frame, f"Selecteaza elementul pentru sablonul '{name}'")
    if region is None:
        return None

    crop = frame[region.top : region.bottom, region.left : region.right]
    directory = Path(templates_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.png"
    cv2.imwrite(str(path), crop)

    print(f"\nSablon salvat: {path}  ({region.width}x{region.height} px)")
    print("Sfat: decupeaza strans, doar partea care nu se schimba niciodata.")
    return path


def calibrate_color(name: str, monitor: int = 1, percentile: float = 5.0) -> Optional[dict]:
    """Deduce intervalul HSV al unei zone colorate (bara de viata, nameplate).

    Taiem cate `percentile` la sută de la fiecare capat inainte sa luam minimul
    si maximul: altfel un singur pixel de margine, mai inchis, largeste inutil
    intervalul si masca prinde jumatate de ecran.
    """
    frame = _grab_after_countdown(monitor)
    region = _select(frame, f"Selecteaza o zona plina de culoarea '{name}'")
    if region is None:
        return None

    crop = frame[region.top : region.bottom, region.left : region.right]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)

    low = np.percentile(hsv, percentile, axis=0).astype(int)
    high = np.percentile(hsv, 100 - percentile, axis=0).astype(int)

    # Largim putin intervalul, ca sa reziste la umbre si efecte grafice.
    low = np.clip(low - np.array([5, 40, 40]), [0, 0, 0], [179, 255, 255])
    high = np.clip(high + np.array([5, 15, 15]), [0, 0, 0], [179, 255, 255])

    print("\nAdauga in profil, sub `colors:`\n")
    print(f"  {name}:")
    print(f"    low: [{low[0]}, {low[1]}, {low[2]}]")
    print(f"    high: [{high[0]}, {high[1]}, {high[2]}]\n")

    if low[0] > high[0]:
        print("Atentie: nuanta trece prin rosu (H se roteste la 0). Pentru rosu")
        print("foloseste doua intervale sau muta pragurile manual.\n")

    return {"low": low.tolist(), "high": high.tolist()}
