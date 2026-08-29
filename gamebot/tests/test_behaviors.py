"""Comportamentele, verificate pe ecrane sintetice si input in gol.

Toate testele ruleaza cu `dry_run=True`: controllerul noteaza ce ar fi trimis,
dar nu atinge nimic. Asa putem verifica deciziile fara joc pornit.
"""

import pytest

from gamebot.behaviors.combat import CombatBehavior
from gamebot.behaviors.gather import GatherBehavior
from gamebot.behaviors.survival import SurvivalBehavior
from gamebot.behaviors.travel import TravelBehavior
from gamebot.core.capture import ReplayCapture
from gamebot.core.engine import BotContext
from gamebot.core.input_ctl import InputController
from gamebot.core.navigation import RoutePlayer
from gamebot.core.route import InputEvent, Route, Waypoint
from gamebot.core.safety import KillSwitch, SessionGuard, Watchdog
from gamebot.core.vision import TemplateLibrary
from gamebot.tests.conftest import make_frame


def build_ctx(profile, frame, tmp_path, player=None) -> BotContext:
    profile.raw.setdefault("survival", {})["heal_wait"] = 0.01
    return BotContext(
        profile=profile,
        capture=ReplayCapture([frame]),
        controller=InputController(dry_run=True),
        templates=TemplateLibrary(tmp_path),
        kill_switch=KillSwitch(),
        watchdog=Watchdog(),
        session=SessionGuard(),
        player=player,
    )


def taste_apasate(ctx) -> list[str]:
    return [value for kind, value in ctx.controller.backend.events if kind == "key_down"]


# ------------------------------------------------------------ supravietuire


def test_nu_se_vindeca_la_viata_plina(test_profile, tmp_path):
    ctx = build_ctx(test_profile, make_frame(1.0), tmp_path)
    ctx.refresh()
    assert not SurvivalBehavior().should_run(ctx)


def test_se_vindeca_sub_prag(test_profile, tmp_path):
    ctx = build_ctx(test_profile, make_frame(0.3), tmp_path)
    ctx.refresh()
    behavior = SurvivalBehavior()

    assert behavior.should_run(ctx)
    behavior.run(ctx)

    assert "5" in taste_apasate(ctx)
    assert ctx.stats.heals == 1


def test_nu_spameaza_vindecarea_in_cooldown(test_profile, tmp_path):
    test_profile.raw["survival"]["heal_cooldown"] = 30.0
    ctx = build_ctx(test_profile, make_frame(0.3), tmp_path)
    ctx.refresh()
    behavior = SurvivalBehavior()

    behavior.run(ctx)
    behavior.run(ctx)  # imediat dupa: skill-ul e pe cooldown

    assert ctx.stats.heals == 1


def test_viata_zero_inseamna_moarte_nu_vindecare(test_profile, tmp_path):
    ctx = build_ctx(test_profile, make_frame(0.0), tmp_path)
    ctx.refresh()
    SurvivalBehavior().run(ctx)

    assert ctx.stats.heals == 0
    assert ctx.watchdog.deaths == 1
    # Fara secventa de reinviere in profil, botul se opreste in loc sa ghiceasca.
    assert ctx.kill_switch.stopped


def test_supravietuirea_se_dezactiveaza_fara_bara_de_viata(test_profile, tmp_path):
    test_profile.regions.pop("health_bar")
    ctx = build_ctx(test_profile, make_frame(0.3), tmp_path)
    assert not SurvivalBehavior().enabled(ctx)


# -------------------------------------------------------------------- cules


def test_culege_nodul_cel_mai_apropiat_de_centru(test_profile, tmp_path):
    ctx = build_ctx(test_profile, make_frame(1.0, nodes=3), tmp_path)
    ctx.refresh()
    behavior = GatherBehavior()

    assert behavior.should_run(ctx)
    behavior.run(ctx)

    assert ctx.stats.gathers == 1
    click = [pos for kind, pos in ctx.controller.backend.events if kind == "move"][-1]
    centru_x = ctx.screen_center()[0]
    # Nodurile sunt la x=40, 100, 160 pe un ecran lat de 400 (centru 200), deci
    # cel de la 160 e cel mai aproape de centru.
    assert abs(click[0] - 175) < 25, f"a dat click aiurea: {click}"


def test_nu_culege_daca_nu_vede_noduri(test_profile, tmp_path):
    ctx = build_ctx(test_profile, make_frame(1.0, nodes=0), tmp_path)
    ctx.refresh()
    assert not GatherBehavior().should_run(ctx)


def test_nodul_incercat_e_ignorat_o_vreme(test_profile, tmp_path):
    """Fara lista neagra, botul ar da click la infinit pe acelasi nod blocat."""
    ctx = build_ctx(test_profile, make_frame(1.0, nodes=1), tmp_path)
    ctx.refresh()
    behavior = GatherBehavior()

    behavior.run(ctx)
    ctx.refresh()

    assert behavior._visible_nodes(ctx) == []


def test_culesul_respecta_zona(test_profile, tmp_path):
    test_profile.raw["gather"]["anywhere"] = False
    ctx = build_ctx(test_profile, make_frame(1.0, nodes=2), tmp_path)
    ctx.refresh()
    behavior = GatherBehavior()

    ctx.current_waypoint = Waypoint(0, "combat")
    assert not behavior.should_run(ctx)

    ctx.current_waypoint = Waypoint(1, "gather")
    assert behavior.should_run(ctx)


# -------------------------------------------------------------------- lupta


def test_lupta_are_nevoie_de_tinta_sau_de_mob_vizibil(test_profile, tmp_path):
    test_profile.raw["combat"] = {"anywhere": True}
    test_profile.keys.pop("target_next", None)
    ctx = build_ctx(test_profile, make_frame(1.0, target=False), tmp_path)
    ctx.refresh()
    # Profilul de test n-are culoare de nameplate, deci nu are ce ataca.
    assert not CombatBehavior().should_run(ctx)


def test_lupta_porneste_cand_exista_tinta(test_profile, tmp_path):
    test_profile.raw["combat"] = {"anywhere": True}
    ctx = build_ctx(test_profile, make_frame(1.0, target=True), tmp_path)
    ctx.refresh()
    assert CombatBehavior().should_run(ctx)


# ---------------------------------------------------------------- traseu


def ruta_scurta() -> Route:
    """Doua repere cu evenimente instantanee, ca testul sa nu astepte."""
    return Route(
        name="test",
        loop=True,
        waypoints=[
            Waypoint(0, "travel", events=[InputEvent("key_down", 0.0, key="w"),
                                          InputEvent("key_up", 0.0, key="w")]),
            Waypoint(1, "combat", dwell=30.0, events=[InputEvent("key_down", 0.0, key="w"),
                                                      InputEvent("key_up", 0.0, key="w")]),
        ],
    )


def test_mersul_avanseaza_pe_traseu(test_profile, tmp_path):
    controller = InputController(dry_run=True)
    player = RoutePlayer(ruta_scurta(), controller)
    ctx = build_ctx(test_profile, make_frame(), tmp_path, player=player)
    ctx.controller = controller

    TravelBehavior().run(ctx)

    assert player.current_index == 1
    assert ctx.current_waypoint.kind == "combat"


def test_stationarea_opreste_mersul(test_profile, tmp_path):
    """La un reper cu dwell, botul ramane pe loc ca sa farmeze acolo."""
    controller = InputController(dry_run=True)
    player = RoutePlayer(ruta_scurta(), controller)
    ctx = build_ctx(test_profile, make_frame(), tmp_path, player=player)
    ctx.controller = controller
    behavior = TravelBehavior()

    behavior.run(ctx)  # ajunge la reperul 1, care are dwell 30s

    assert ctx.dwelling()
    assert not behavior.should_run(ctx)


def test_tura_completa_se_numara(test_profile, tmp_path):
    controller = InputController(dry_run=True)
    player = RoutePlayer(ruta_scurta(), controller)
    ctx = build_ctx(test_profile, make_frame(), tmp_path, player=player)
    ctx.controller = controller
    behavior = TravelBehavior()

    behavior.run(ctx)   # 0 -> 1
    ctx.dwell_until = 0.0
    behavior.run(ctx)   # 1 -> 0, adica o tura incheiata

    assert player.laps == 1
    assert ctx.stats.laps == 1


def test_redarea_trimite_tastele_inregistrate(test_profile, tmp_path):
    controller = InputController(dry_run=True)
    player = RoutePlayer(ruta_scurta(), controller)

    player.play_segment(ruta_scurta().waypoints[0])

    kinds = [k for k, _ in controller.backend.events]
    assert "key_down" in kinds and "key_up" in kinds


def test_oprirea_intrerupe_redarea_si_elibereaza_tastele(test_profile, tmp_path):
    controller = InputController(dry_run=True)
    kill = KillSwitch()
    kill.stop()
    player = RoutePlayer(ruta_scurta(), controller, should_continue=kill.running)

    assert player.play_segment(ruta_scurta().waypoints[0]) is False
    assert controller._held_keys == set()
