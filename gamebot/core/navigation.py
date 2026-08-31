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

    def __init__(self, route: Route, capture, anchor_region: Optional[Region],
                 threshold: float = 0.72, thumb_width: int = 240) -> None:
        self.route = route
        self.capture = capture
        # Fara `regions.minimap` in profil, ancora e tot ecranul jocului. Merge
        # surprinzator de bine: forma terenului si asezarea cladirilor
        # identifica locul la fel de sigur ca o minimapa, iar micsorarea sterge
        # jucatorii care trec prin cadru.
        self.anchor_region = anchor_region
        self.threshold = threshold
        self.thumb_width = thumb_width
        self._anchors: dict[int, np.ndarray] = {}
        self._portal_anchors: dict[int, np.ndarray] = {}
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

            portal_path = self.route.portal_anchor_path(wp)
            if portal_path and portal_path.exists():
                image = cv2.imread(str(portal_path))
                if image is not None:
                    self._portal_anchors[wp.index] = image

        log.info(
            "Ancore incarcate: %d din %d repere (%d de portal)",
            len(self._anchors), len(self.route), len(self._portal_anchors),
        )

    @property
    def has_anchors(self) -> bool:
        return bool(self._anchors)

    def _current_view(self) -> Optional[np.ndarray]:
        """Ecranul de acum, micsorat la fel ca ancorele cu care il comparam."""
        try:
            return vision.thumbnail(self.capture.grab(self.anchor_region), self.thumb_width)
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

    def verify_portal(self, index: int) -> Optional[bool]:
        """Am ajuns pe harta de dincolo de portalul reperului `index`?

        Intoarce None cand nu avem cu ce compara, ca sa poata fi deosebit de un
        raspuns negativ ferm.
        """
        anchor = self._portal_anchors.get(index)
        if anchor is None:
            return None
        view = self._current_view()
        if view is None:
            return None
        score = vision.similarity(anchor, view)
        log.debug("Verificare portal %d: scor %.3f", index, score)
        return score >= self.threshold

    def relocate(self, near: Optional[int] = None, window: int = 0) -> Optional[Fix]:
        """Cauta reperul a carui ancora seamana cel mai bine cu ecranul.

        Cand traseul trece prin portale, ruta acopera mai multe harti, iar o
        cautare oarba pe tot traseul poate "gasi" un reper de pe alta harta doar
        pentru ca minimapa are colturi asemanatoare. De aceea, cand stim
        aproximativ unde suntem (`near`), cautam intai doar in vecinatate si
        largim la toata ruta abia daca acolo nu iese nimic convingator.
        """
        view = self._current_view()
        if view is None or not self._anchors:
            return None

        def best_among(indices) -> Optional[Fix]:
            best_index, best_score = -1, 0.0
            for index in indices:
                anchor = self._anchors.get(index)
                if anchor is None:
                    continue
                score = vision.similarity(anchor, view)
                if score > best_score:
                    best_index, best_score = index, score
            if best_index < 0:
                return None
            return Fix(best_index, best_score, best_score >= self.threshold)

        if near is not None and window > 0:
            total = len(self.route)
            vecini = [(near + offset) % total for offset in range(-window, window + 1)]
            fix = best_among(vecini)
            if fix and fix.confident:
                log.info("Relocalizare in vecinatate: reper %d (scor %.3f)", fix.index, fix.score)
                return fix

        fix = best_among(self._anchors.keys())
        if fix:
            log.info("Relocalizare pe toata ruta: reper %d cu scor %.3f (%s)", fix.index,
                     fix.score, "sigur" if fix.confident else "nesigur")
        return fix


class RoutePlayer:
    """Reda secventele inregistrate, cu corectie la fiecare reper."""

    # Cat timp trebuie sa stea ecranul neschimbat ca sa consideram incarcarea
    # incheiata, si cat mai asteptam dupa aceea ca personajul sa fie jucabil.
    LOAD_STABLE_SECONDS = 1.5
    LOAD_SETTLE_SECONDS = 1.0

    def __init__(
        self,
        route: Route,
        controller: InputController,
        localizer: Optional[Localizer] = None,
        speed: float = 1.0,
        should_continue: Optional[Callable[[], bool]] = None,
        on_waypoint: Optional[Callable[[Waypoint], None]] = None,
        capture=None,
        templates=None,
    ) -> None:
        self.route = route
        self.controller = controller
        self.localizer = localizer
        # Captura e folosita doar la portale, ca sa vedem cand s-a terminat
        # ecranul de incarcare. Restul navigatiei trece prin localizer.
        self.capture = capture if capture is not None else getattr(localizer, "capture", None)
        self.templates = templates
        self.speed = max(0.5, min(speed, 2.0))
        self.should_continue = should_continue or (lambda: True)
        self.on_waypoint = on_waypoint

        self.current_index = 0
        self.laps = 0
        self.lost_count = 0
        self.portals_taken = 0

        # Chemat periodic in timpul redarii unui segment. Fara el, cat timp se
        # reda un segment lung nu se poate intampla nimic altceva - iar o ruta
        # cu un singur reper e un segment cat toata tura, deci botul ar trece
        # pe langa tot ce e pe jos fara sa ridice nimic.
        self.on_tick: Optional[Callable[[], None]] = None
        self.tick_interval: float = 1.0
        self._last_tick = 0.0
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

            if self.on_tick is not None:
                acum = time.monotonic()
                if acum - self._last_tick >= self.tick_interval:
                    self._last_tick = acum
                    try:
                        self.on_tick()
                    except Exception:
                        log.exception("Actiunea periodica din timpul mersului a esuat.")

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

        # Portalul se trece dupa ce am confirmat ca stam in fata lui.
        if arrived.portal is not None and not self._enter_portal(arrived):
            return None

        if self.on_waypoint:
            self.on_waypoint(arrived)
        return arrived

    # -------------------------------------------------------------- portale

    def _enter_portal(self, waypoint: Waypoint) -> bool:
        """Da click pe portal si asteapta harta noua. False = nu am reusit.

        Un portal nu poate fi redat ca un click oarecare: intre click si harta
        noua e o incarcare a carei durata variaza de la o data la alta. Asa ca
        dam click, asteptam sa se linisteasca ecranul, si confirmam cu ancora
        de destinatie inregistrata atunci cand ai trecut tu.
        """
        portal = waypoint.portal
        assert portal is not None

        for attempt in range(1, 3):
            if not self.should_continue():
                return False

            x, y = self._portal_click_point(portal)
            print(f"  > intru in portal (reperul {waypoint.index})")
            self.controller.click(x, y)

            self._wait_for_load(portal.load_seconds)

            arrived = self.localizer.verify_portal(waypoint.index) if self.localizer else None
            if arrived is None:
                # Fara ancora de destinatie nu avem cum confirma; mergem pe
                # incredere, dar spunem asta o data, ca sa se stie de ce.
                log.info("Portalul %d nu are ancora de destinatie; nu pot confirma trecerea.",
                         waypoint.index)
                self.portals_taken += 1
                return True
            if arrived:
                self.portals_taken += 1
                print("    ajuns pe harta noua")
                return True

            # Nu am ajuns. Daca inca suntem pe harta veche, clicul a ratat
            # portalul si merita reincercat; altfel suntem in alta parte si o
            # a doua apasare ar face lucrurile mai rele.
            still_here = self.localizer.verify(waypoint.index) if self.localizer else False
            if not still_here:
                log.error("Dupa portal nu recunosc nici harta veche, nici pe cea noua.")
                return False
            log.warning("Clicul pe portal pare sa fi ratat (incercarea %d).", attempt)
            humanize.sleep(1.5, 0.2)

        print("  !! nu am reusit sa trec portalul")
        return False

    def _portal_click_point(self, portal) -> tuple[int, int]:
        """Unde dam click: pe sablon daca il gasim, altfel unde ai dat tu.

        Sablonul ajuta cand portalul nu e fix pe ecran (camera se roteste
        putin, personajul se opreste cu un pas mai incolo).
        """
        if portal.template and self.templates is not None and self.capture is not None:
            template = self.templates.get(portal.template)
            if template is not None:
                match = vision.find_template(self.capture.grab(), template, 0.8)
                if match:
                    return match.center
                log.debug("Sablonul de portal '%s' nu a fost gasit; folosesc pozitia inregistrata.",
                          portal.template)
        return self._scaled(*portal.click)

    def _wait_for_load(self, max_seconds: float) -> float:
        """Asteapta pana cand ecranul se schimba si apoi se linisteste.

        Intoarce cate secunde a durat. Fara captura, asteptam pur si simplu
        jumatate din bugetul de timp - suficient in majoritatea cazurilor.
        """
        if self.capture is None:
            humanize.sleep(max_seconds / 2, 0.15)
            return max_seconds / 2

        started = time.monotonic()
        previous = self.capture.grab()
        stable_since = 0.0

        while time.monotonic() - started < max_seconds:
            if not self.should_continue():
                break
            time.sleep(0.3)
            current = self.capture.grab()
            if vision.frames_differ(previous, current, 3.0):
                stable_since = 0.0
            elif stable_since == 0.0:
                stable_since = time.monotonic()
            elif time.monotonic() - stable_since > self.LOAD_STABLE_SECONDS:
                break
            previous = current

        elapsed = time.monotonic() - started
        log.debug("Incarcare terminata in %.1fs.", elapsed)
        # Harta e afisata, dar personajul poate fi inca "inghetat" o clipa.
        humanize.sleep(self.LOAD_SETTLE_SECONDS, 0.25)
        return elapsed

    # ------------------------------------------------------------ resincronizare

    def resync(self) -> bool:
        """Mai suntem unde credeam? Folosit dupa o lupta care ne-a tras din drum.

        O lupta te scoate din traseu: fugi dupa mob, te intorci din alta parte,
        cu camera rotita. Daca am relua secventa inregistrata de acolo, am
        merge in cu totul alta directie. Verificam intai, si abia apoi mergem.
        """
        if not self.localizer or not self.localizer.has_anchors:
            return True
        if self.localizer.verify(self.current_index):
            return True

        fix = self.localizer.relocate(near=self.current_index, window=6)
        if fix and fix.confident:
            if fix.index != self.current_index:
                print(f"  ~ dupa lupta sunt la reperul {fix.index}, continui de acolo")
            self.current_index = fix.index
            return True

        log.warning("Dupa lupta nu recunosc pozitia.")
        return False

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

        fix = self.localizer.relocate(near=self.current_index, window=8)
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
