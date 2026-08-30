"""Trecerea prin portal: click, incarcare, confirmarea hartii noi."""

import cv2
import pytest

from gamebot.core.input_ctl import InputController
from gamebot.core.navigation import Localizer, RoutePlayer
from gamebot.core.route import InputEvent, Portal, Route, Waypoint
from gamebot.tests.conftest import make_frame


class CapturaFalsa:
    """Ecran controlat de test: ramane pe harta veche pana cerem schimbarea."""

    def __init__(self, harta_veche, harta_noua):
        self.frame = harta_veche
        self._harta_noua = harta_noua
        self.grabs = 0

    def treci_pe_harta_noua(self):
        self.frame = self._harta_noua

    def grab(self, region=None):
        self.grabs += 1
        return self.frame

    def grab_cached(self, region=None, max_age=0.0):
        return self.grab(region)


class ControllerCuPortal(InputController):
    """Controller de proba: un click pe portal muta ecranul pe harta noua."""

    def __init__(self, capture, portalul_functioneaza=True):
        super().__init__(dry_run=True)
        self._capture = capture
        self._portalul_functioneaza = portalul_functioneaza
        self.clicks = []

    def click(self, x=None, y=None, button="left", double=False):
        self.clicks.append((x, y))
        if self._portalul_functioneaza:
            self._capture.treci_pe_harta_noua()


@pytest.fixture
def ruta_cu_portal(tmp_path):
    """O ruta de doua repere: drum, apoi un portal catre alta harta."""
    harta_veche = make_frame(1.0, nodes=1)
    harta_noua = make_frame(0.6, nodes=3, target=True)

    cv2.imwrite(str(tmp_path / "anchor_000.png"), harta_veche)
    cv2.imwrite(str(tmp_path / "anchor_001.png"), harta_veche)
    cv2.imwrite(str(tmp_path / "portal_001_dest.png"), harta_noua)

    route = Route(
        name="cu_portal",
        loop=False,
        waypoints=[
            Waypoint(0, "travel", anchor="anchor_000.png",
                     events=[InputEvent("key_down", 0.0, key="w"),
                             InputEvent("key_up", 0.0, key="w")]),
            Waypoint(1, "portal", anchor="anchor_001.png",
                     portal=Portal(click=(640, 400), dest_anchor="portal_001_dest.png",
                                   load_seconds=6.0)),
        ],
    )
    route.save(tmp_path)
    return Route.load(tmp_path), harta_veche, harta_noua


def build_player(route, capture, portalul_functioneaza=True):
    localizer = Localizer(route, capture, anchor_region=None)
    controller = ControllerCuPortal(capture, portalul_functioneaza)
    player = RoutePlayer(route, controller, localizer, capture=capture)
    # Testul nu are de ce sa astepte stabilizarea reala a ecranului.
    player.LOAD_STABLE_SECONDS = 0.05
    player.LOAD_SETTLE_SECONDS = 0.01
    return player, controller


def test_portalul_e_serializat_in_ruta(ruta_cu_portal):
    route, _, _ = ruta_cu_portal
    portal = route.waypoints[1].portal

    assert portal is not None
    assert portal.click == (640, 400)
    assert portal.dest_anchor == "portal_001_dest.png"
    assert portal.load_seconds == 6.0


def test_ancorele_de_portal_sunt_incarcate(ruta_cu_portal):
    route, _, _ = ruta_cu_portal
    localizer = Localizer(route, CapturaFalsa(make_frame(), make_frame()), None)
    assert 1 in localizer._portal_anchors


def test_trecerea_prin_portal_da_click_si_confirma_harta_noua(ruta_cu_portal):
    route, _, _ = ruta_cu_portal
    capture = CapturaFalsa(make_frame(1.0, nodes=1), make_frame(0.6, nodes=3, target=True))
    player, controller = build_player(route, capture)

    ajuns = player.advance()  # reperul 0 -> reperul 1, care e portalul

    assert ajuns.kind == "portal"
    assert controller.clicks == [(640, 400)]
    assert player.portals_taken == 1


def test_clicul_ratat_pe_portal_se_reincearca(ruta_cu_portal):
    """Daca ecranul a ramas pe harta veche, clicul n-a nimerit portalul."""
    route, _, _ = ruta_cu_portal
    capture = CapturaFalsa(make_frame(1.0, nodes=1), make_frame(0.6, nodes=3))
    player, controller = build_player(route, capture, portalul_functioneaza=False)

    ajuns = player.advance()

    assert ajuns is None, "ar fi trebuit sa raporteze esec dupa reincercari"
    assert len(controller.clicks) == 2, "portalul se incearca de doua ori"


def test_portalul_fara_ancora_de_destinatie_merge_pe_incredere(ruta_cu_portal):
    """Fara poza hartii noi nu avem cum confirma, dar nu blocam traseul."""
    route, _, _ = ruta_cu_portal
    route.waypoints[1].portal.dest_anchor = None
    capture = CapturaFalsa(make_frame(1.0, nodes=1), make_frame(0.6, nodes=3))
    player, controller = build_player(route, capture)

    localizer = Localizer(route, capture, None)
    localizer._portal_anchors.clear()
    player.localizer = localizer

    assert player.advance() is not None
    assert player.portals_taken == 1


def test_clicul_se_scaleaza_la_alta_rezolutie(ruta_cu_portal):
    route, _, _ = ruta_cu_portal
    route.screen = {"width": 1280, "height": 720}
    capture = CapturaFalsa(make_frame(1.0, nodes=1), make_frame(0.6, nodes=3, target=True))
    player, controller = build_player(route, capture)
    player.set_screen(2560, 1440)

    player.advance()

    assert controller.clicks == [(1280, 800)]
