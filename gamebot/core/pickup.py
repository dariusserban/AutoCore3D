"""Gasirea obiectelor de pe jos, folosita si de bot, si de modul cu tasta.

Aceeasi logica in amandoua locurile: cauta etichetele colorate ale obiectelor,
pastreaza-le pe cele dintr-o raza in jurul personajului, si ignora-le pe cele
incercate recent fara succes.

Raza e in pixeli de ecran, la fel ca cercul desenat de overlay - deci ce vezi
pe ecran e exact ce va fi cules, nu o aproximare.
"""

from __future__ import annotations

import math
import time
from typing import Iterable, Optional

import numpy as np

from . import vision


class Blacklist:
    """Tine minte pozitiile incercate, ca sa nu insistam la nesfarsit.

    Un obiect in spatele unui gard nu se ridica oricat ai da click pe el. Fara
    lista asta, primul obiect de neluat opreste tot restul culesului.
    """

    def __init__(self, seconds: float = 20.0, distance: float = 30.0) -> None:
        self.seconds = seconds
        self.distance = distance
        self._puncte: list[tuple[int, int, float]] = []

    def add(self, x: int, y: int) -> None:
        self._puncte.append((int(x), int(y), time.monotonic()))

    def contains(self, x: int, y: int) -> bool:
        acum = time.monotonic()
        self._puncte = [p for p in self._puncte if acum - p[2] < self.seconds]
        return any(math.hypot(x - px, y - py) < self.distance for px, py, _ in self._puncte)

    def clear(self) -> None:
        self._puncte.clear()

    def __len__(self) -> int:
        return len(self._puncte)


def find_loot(
    image: np.ndarray,
    culori: Iterable[tuple[Iterable[int], Iterable[int]]],
    center: tuple[int, int],
    radius: float = 0.0,
    min_area: int = 25,
    max_area: Optional[int] = None,
    blacklist: Optional[Blacklist] = None,
    offset: tuple[int, int] = (0, 0),
    exclude_ring: Optional[tuple[float, float]] = None,
) -> list[vision.Match]:
    """Etichetele de obiect din imagine, filtrate dupa raza si lista neagra.

    `offset` muta rezultatele in coordonate de ecran, cand imaginea e decupajul
    unei ferestre si nu tot ecranul.

    `max_area` arunca petele prea mari ca sa fie un obiect pe jos. Fara el, un
    monstru verde e prins de intervalul pentru etichete verzi si botul se duce
    sa-l "ridice" - detectia pe culoare nu are cum sa faca diferenta singura.

    `exclude_ring` primeste (raza, toleranta) si arunca ce cade pe inelul ala.
    Serveste la un singur lucru, dar esential: cercul desenat de noi peste joc
    intra si el in captura de ecran, iar culoarea lui poate cadea in intervalul
    cautat. Fara excluderea asta, botul isi vede propriul cerc drept obiecte si
    alearga in cerc dupa el.
    """
    if image is None or image.size == 0:
        return []

    gasite: list[vision.Match] = []
    for low, high in culori:
        for blob in vision.color_blobs(image, low, high, min_area=min_area):
            x = blob.x + offset[0]
            y = blob.y + offset[1]
            gasite.append(vision.Match(x, y, blob.width, blob.height, blob.score))

    cx, cy = center
    rezultat = []
    for blob in gasite:
        bx, by = blob.center
        distanta = math.hypot(bx - cx, by - cy)

        if radius > 0 and distanta > radius:
            continue
        if max_area is not None and blob.width * blob.height > max_area:
            continue
        if exclude_ring is not None:
            raza_inel, toleranta = exclude_ring
            if abs(distanta - raza_inel) <= toleranta:
                continue
        if blacklist is not None and blacklist.contains(bx, by):
            continue
        rezultat.append(blob)

    # Cele mai apropiate primele: personajul se deplaseaza cel mai putin.
    rezultat.sort(key=lambda b: math.hypot(b.center[0] - cx, b.center[1] - cy))
    return rezultat


def acoperire(image: np.ndarray, low: Iterable[int], high: Iterable[int]) -> float:
    """Ce fractiune din imagine cade in intervalul de culoare dat.

    Serveste la verificarea unei probe de culoare. Eticheta unui obiect ocupa o
    parte foarte mica din ecran; daca intervalul masurat prinde 30% din imagine,
    proba a fost luata de pe fundal si e inutilizabila - dar arata la fel de
    "masurata" ca una buna, deci fara verificarea asta ar ajunge linistita in
    profil si n-ar gasi nimic niciodata.
    """
    if image is None or image.size == 0:
        return 0.0
    masca = vision.hsv_mask(image, low, high)
    return float((masca > 0).sum()) / float(masca.size)


def culori_din_profil(profile, nume_culori: Iterable[str]) -> list[tuple[list[int], list[int]]]:
    """Traduce numele culorilor din profil in perechi de intervale HSV."""
    culori = []
    for nume in nume_culori:
        culoare = profile.color(nume)
        if culoare is not None:
            culori.append((list(culoare.low), list(culoare.high)))
    return culori
