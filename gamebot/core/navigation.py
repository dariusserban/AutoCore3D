"""Redarea rutei si "unde sunt eu acum".

Doua piese:

  Localizer  - compara ce se vede acum (minimapa) cu ancorele inregistrate si
               spune la ce reper suntem. Fara acces la coordonatele reale ale
               personajului, asta e cea mai buna estimare posibila.

  RoutePlayer - reda segmentele inregistrate, verifica la fiecare reper daca am
               ajuns unde trebuie si incearca sa se recupereze cand nu.

Problema pe care o rezolva verificarea prin ancore: un mob care te agata pe
drum sau un lag de doua secunde decaleaza toata secventa. Fara corectie, botul
ajunge dupa cinci ture in cu totul alta parte a hartii si continua sa apese
taste ca si cum nimic nu s-ar fi intamplat.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import humanize, vision
from .capture import Region
from .input_ctl import InputController
from .route import InputEvent, Route, Waypoint

log = logging.getLogger(__name__)

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


@dataclass
class Fix:
    """Rezultatul unei incercari de localizare."""

    index: int
    score: float
    confident: bool


class Localizer:
    """Estimeaza reperul curent comparand ecranul cu ancorele rutei."""

    def __init__(self, route: Route, capture, anchor_region: Optional[Region], threshold: float = 0.72) -> None:
        self.route = route
        self.capture = capture
        self.anchor_region = anchor_region
        self.threshold = threshold
        self._anchors: dict[int, np.ndarray] = {}
        self._load_anchors()

    def _load_anchors(self) -> None:
        if cv2 is None:
            return
        for wp in self.route.waypoints:
            path = self.route.anchor_path(wp)
            if path and path.exists():
                image = cv2.imread(str(path))
                if image is not None:
                    self._anchors[wp.index] = image
        log.info("Ancore incarcate: %d din %d repere", len(self._anchors), len(self.route))

    @property
    def has_anchors(self) -> bool:
        return bool(self._anchors)

    def _current_view(self) -> Optional[np.ndarray]:
        try:
            return self.capture.grab(self.anchor_region)
        except Exception as exc:
            log.warning("Captura pentru localizare a esuat: %s", exc)
            return None

    def score_at(self, index: int) -> float:
        """Cat de bine seamana ecranul de acum cu ancora reperului `index`."""
        anchor = self._anchors.get(index)
        if anchor is None:
            return 0.0
        view = self._current_view()
        if view is None:
            return 0.0
        return vision.similarity(anchor, view)

    def verify(self, index: int) -> bool:
        """Suntem la reperul asteptat?"""
        if index not in self._anchors:
            return True  # fara ancora nu avem ce contrazice; mergem mai departe
        score = self.score_at(index)
        ok = score >= self.threshold
        log.debug("Verificare reper %d: scor %.3f (prag %.2f) -> %s", index, score, self.threshold, ok)
        return ok

    def relocate(self) -> Optional[Fix]:
        """Cauta prin toate ancorele reperul care seamana cel mai bine.

        Apelat doar cand ne-am pierdut: e o comparatie pe toata ruta, deci
        costa, dar se intampla rar.
        """
        view = self._current_view()
        if view is None or not self._anchors:
            return None

        best_index, best_score = -1, 0.0
        for index, anchor in self._anchors.items():
            score = vision.similarity(anchor, view)
            if score > best_score:
                best_index, best_score = index, score

        if best_index < 0:
            return None
        fix = Fix(best_index, best_score, best_score >= self.threshold)
        log.info("Relocalizare: reper %d cu scor %.3f (%s)", fix.index, fix.score,
                 "sigur" if fix.confident else "nesigur")
        return fix


class RoutePlayer:
    """Reda secventele inregistrate, cu corectie la fiecare reper."""

    def __init__(
        self,
        route: Route,
        controller: InputController,
        localizer: Optional[Localizer] = None,
        speed: float = 1.0,
        should_continue: Optional[Callable[[], bool]] = None,
        on_waypoint: Optional[Callable[[Waypoint], None]] = None,
    ) -> None:
        self.route = route
        self.controller = controller
        self.localizer = localizer
        self.speed = max(0.5, min(speed, 2.0))
        self.should_continue = should_continue or (lambda: True)
        self.on_waypoint = on_waypoint

        self.current_index = 0
        self.laps = 0
        self.lost_count = 0
        # 1:1 pana cand cineva ne spune rezolutia curenta prin set_screen().
        self._scale = (1.0, 1.0)

    def set_screen(self, width: int, height: int) -> None:
        """Anunta rezolutia curenta, ca sa scalam coordonatele inregistrate."""
        recorded = self.route.screen
        if not recorded:
            return
        rw, rh = float(recorded.get("width", width)), float(recorded.get("height", height))
        if rw <= 0 or rh <= 0:
            return
        self._scale = (width / rw, height / rh)
        if self._scale != (1.0, 1.0):
            log.warning(
                "Rezolutia difera de cea de la inregistrare (%dx%d vs %dx%d). "
                "Scalez coordonatele, dar interfata poate sa nu se potriveasca.",
                width, height, int(rw), int(rh),
            )

    def _scaled(self, x: Optional[int], y: Optional[int]) -> tuple[int, int]:
        sx, sy = self._scale
        return int(round((x or 0) * sx)), int(round((y or 0) * sy))

    # ------------------------------------------------------------- redare

    def play_segment(self, waypoint: Waypoint) -> bool:
        """Reda drumul de la `waypoint` catre urmatorul.

        Intoarce False daca a fost intrerupt (kill switch, pauza de siguranta).
        """
        # Variem usor viteza fiecarei ture; un traseu redat identic la
        # milisecunda, de 200 de ori, e mai regulat decat orice om.
        lap_speed = self.speed * humanize.delay(1.0, 0.06)

        for event in waypoint.events:
            if not self.should_continue():
                self.controller.release_all()
                return False
            wait = event.dt / lap_speed
            if wait > 0.001:
                time.sleep(wait)
            self._dispatch(event)

        self.controller.release_all()
        return True

    def _dispatch(self, event: InputEvent) -> None:
        c = self.controller
        try:
            if event.kind == "key_down" and event.key:
                c.key_down(event.key)
            elif event.kind == "key_up" and event.key:
                c.key_up(event.key)
            elif event.kind == "move":
                x, y = self._scaled(event.x, event.y)
                # Traiectoria e deja umana - a facut-o mana ta la inregistrare -
                # deci o redam punct cu punct, fara sa mai sintetizam curbe.
                c.backend.move_to(x, y)
            elif event.kind == "mouse_down":
                x, y = self._scaled(event.x, event.y)
                c.backend.move_to(x, y)
                c.backend.mouse_down(event.button or "left")
            elif event.kind == "mouse_up":
                c.backend.mouse_up(event.button or "left")
            elif event.kind == "scroll":
                c.scroll(event.amount or 0)
        except Exception as exc:
            log.warning("Eveniment esuat (%s): %s", event.kind, exc)

    def advance(self) -> Optional[Waypoint]:
        """Un pas complet: reda segmentul, verifica ancora, trece mai departe.

        Intoarce reperul la care am ajuns, sau None daca rularea s-a oprit.
        """
        if not self.route.waypoints:
            return None

        current = self.route.get(self.current_index)
        if not self.play_segment(current):
            return None

        next_index = self.route.next_index(self.current_index)
        if next_index == 0 and self.current_index != 0:
            self.laps += 1
            log.info("Tura %d incheiata.", self.laps)

        self.current_index = next_index
        arrived = self.route.get(next_index)

        if self.localizer and self.localizer.has_anchors:
            if not self.localizer.verify(next_index):
                self.lost_count += 1
                if not self._recover():
                    return None
                arrived = self.route.get(self.current_index)
            else:
                self.lost_count = 0

        if self.on_waypoint:
            self.on_waypoint(arrived)
        return arrived

    def _recover(self) -> bool:
        """Am iesit de pe traseu. Incercam sa ne dam seama unde suntem.

        Strategia: cautam prin toate ancorele. Daca gasim una convingatoare,
        sarim direct la reperul ala si continuam de acolo - e mult mai sigur
        decat sa incercam sa "ne intoarcem" pe orbeste. Daca nu gasim nimic,
        raportam esec si lasam bucla principala sa decida (de obicei: oprire).
        """
        log.warning("Nu sunt la reperul asteptat (a %d-a oara la rand).", self.lost_count)
        self.controller.release_all()
        time.sleep(humanize.delay(1.2, 0.3))

        if self.localizer is None:
            return False

        fix = self.localizer.relocate()
        if fix and fix.confident:
            print(f"  ~ recuperat: continui de la reperul {fix.index}")
            self.current_index = fix.index
            self.lost_count = 0
            return True

        if self.lost_count >= 3:
            log.error("Trei incercari de recuperare esuate. Opresc.")
            return False

        # Inca o sansa: poate doar am ramas in urma si segmentul urmator ne
        # aduce inapoi pe traseu.
        return True

    def jump_to_nearest(self) -> Optional[int]:
        """Sincronizeaza pozitia de start cu locul in care e personajul acum.

        Se apeleaza la pornire: daca tu ai lasat personajul la jumatatea
        traseului, nu are rost sa inceapa de la reperul 0.
        """
        if not self.localizer or not self.localizer.has_anchors:
            return None
        fix = self.localizer.relocate()
        if fix and fix.confident:
            self.current_index = fix.index
            print(f"Pornesc de la reperul {fix.index} (potrivire {fix.score:.2f}).")
            return fix.index
        print("Nu recunosc pozitia curenta; pornesc de la reperul 0.")
        return None
