"""Contextul si masina de stari: ce vede botul si ce decide sa faca."""

import pytest

from gamebot.core.capture import ReplayCapture
from gamebot.core.engine import Behavior, BehaviorEngine, BotContext
from gamebot.core.input_ctl import InputController
from gamebot.core.route import Waypoint
from gamebot.core.safety import KillSwitch, SessionGuard, Watchdog
from gamebot.core.vision import TemplateLibrary
from gamebot.tests.conftest import make_frame


def build_ctx(profile, frame, tmp_path) -> BotContext:
    return BotContext(
        profile=profile,
        capture=ReplayCapture([frame]),
        controller=InputController(dry_run=True),
        templates=TemplateLibrary(tmp_path),
        kill_switch=KillSwitch(),
        watchdog=Watchdog(),
        session=SessionGuard(),
    )


# --------------------------------------------------------------- citirea starii


@pytest.mark.parametrize("ratio", [1.0, 0.5, 0.25])
def test_citeste_viata_din_regiunea_din_profil(test_profile, tmp_path, ratio):
    ctx = build_ctx(test_profile, make_frame(ratio), tmp_path)
    ctx.refresh()
    assert ctx.health == pytest.approx(ratio, abs=0.05)


def test_tinta_selectata_se_deduce_din_bara_tintei(test_profile, tmp_path):
    fara = build_ctx(test_profile, make_frame(1.0, target=False), tmp_path)
    fara.refresh()
    assert not fara.has_target()

    cu = build_ctx(test_profile, make_frame(1.0, target=True), tmp_path)
    cu.refresh()
    assert cu.has_target()


def test_gaseste_nodurile_in_coordonate_de_ecran(test_profile, tmp_path):
    ctx = build_ctx(test_profile, make_frame(1.0, nodes=3), tmp_path)
    ctx.refresh()
    blobs = ctx.find_blobs("resource_node", min_area=100)
    assert len(blobs) == 3
    assert all(190 < b.center[1] < 240 for b in blobs)


def test_culoare_nedefinita_nu_arunca(test_profile, tmp_path):
    ctx = build_ctx(test_profile, make_frame(), tmp_path)
    ctx.refresh()
    assert ctx.find_blobs("culoare_inexistenta") == []
    assert ctx.bar_ratio("health_bar", "inexistenta") is None


# ------------------------------------------------------------------ zonele


def test_zona_restrictioneaza_activitatea(test_profile, tmp_path):
    ctx = build_ctx(test_profile, make_frame(), tmp_path)

    ctx.current_waypoint = Waypoint(0, "combat")
    assert ctx.zone_allows("combat")
    # 'gather' e marcat cu anywhere: true in profilul de test, deci trece
    # oriunde; 'upkeep' nu e, deci nu are voie intr-o zona de lupta.
    assert ctx.zone_allows("gather")
    assert not ctx.zone_allows("upkeep")

    ctx.current_waypoint = Waypoint(1, "vendor")
    assert not ctx.zone_allows("combat")
    assert ctx.zone_allows("upkeep")


def test_fara_ruta_orice_e_permis(test_profile, tmp_path):
    ctx = build_ctx(test_profile, make_frame(), tmp_path)
    assert ctx.current_waypoint is None
    assert ctx.zone_allows("combat") and ctx.zone_allows("upkeep")


# ------------------------------------------------------------------ motorul


class Spion(Behavior):
    """Comportament de test care noteaza cand a fost rulat."""

    def __init__(self, name, priority, activ=True):
        self.name = name
        self.priority = priority
        self._activ = activ
        self.rulari = 0

    def enabled(self, ctx):
        return True

    def should_run(self, ctx):
        return self._activ

    def run(self, ctx):
        self.rulari += 1


def test_prioritatea_mai_mare_castiga(test_profile, tmp_path):
    ctx = build_ctx(test_profile, make_frame(), tmp_path)
    mic, mare = Spion("mic", 10), Spion("mare", 90)
    engine = BehaviorEngine(ctx, [mic, mare])

    ales = engine.step()

    assert ales is mare
    assert mare.rulari == 1 and mic.rulari == 0


def test_se_trece_la_urmatorul_cand_primul_nu_are_treaba(test_profile, tmp_path):
    ctx = build_ctx(test_profile, make_frame(), tmp_path)
    inactiv, activ = Spion("inactiv", 90, activ=False), Spion("activ", 10)
    engine = BehaviorEngine(ctx, [inactiv, activ])

    assert engine.step() is activ
    assert activ.rulari == 1


class Defect(Spion):
    def run(self, ctx):
        ctx.controller.key_down("w")  # ramane apasata daca nu curatam
        raise RuntimeError("crapa intentionat")


def test_un_comportament_care_crapa_nu_opreste_botul(test_profile, tmp_path):
    ctx = build_ctx(test_profile, make_frame(), tmp_path)
    defect = Defect("defect", 90)
    engine = BehaviorEngine(ctx, [defect])

    assert engine.step() is None  # exceptia e prinsa, nu propagata
    # Cel mai important: tastele nu raman apasate cu personajul alergand.
    assert ctx.controller._held_keys == set()


def test_comportamentele_dezactivate_nu_intra_in_lista(test_profile, tmp_path):
    class Dezactivat(Spion):
        def enabled(self, ctx):
            return False

    ctx = build_ctx(test_profile, make_frame(), tmp_path)
    engine = BehaviorEngine(ctx, [Dezactivat("nu", 50), Spion("da", 10)])
    assert [b.name for b in engine.active] == ["da"]


# ------------------------------- personajul e in centrul ferestrei, nu al ecranului


def test_centrul_e_al_ecranului_cand_nu_stim_fereastra(test_profile, tmp_path):
    ctx = build_ctx(test_profile, make_frame(), tmp_path)
    assert ctx.screen_center() == (200, 150)  # cadrul sintetic e 400x300


def test_centrul_urmeaza_fereastra_jocului(test_profile, tmp_path):
    """Toate razele pleaca de aici: cules, angajare in lupta, tintire.

    Cu jocul intr-o fereastra mutata intr-o parte, centrul ecranului e in cu
    totul alta parte decat personajul - si fiecare raza ar cadea alaturi fara
    ca nimic sa dea eroare.
    """
    from gamebot.core.capture import Region

    ctx = build_ctx(test_profile, make_frame(), tmp_path)
    ctx.game_area = Region(950, 102, 890, 640)

    assert ctx.screen_center() == (1395, 422)


def test_motorul_face_comportamentele_accesibile_dupa_nume(test_profile, tmp_path):
    ctx = build_ctx(test_profile, make_frame(), tmp_path)
    unu, doi = Spion("unu", 10), Spion("doi", 20)

    BehaviorEngine(ctx, [unu, doi])

    assert ctx.behaviors["unu"] is unu
    assert ctx.behaviors["doi"] is doi
