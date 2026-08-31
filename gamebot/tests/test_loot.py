"""Adunarea automata a obiectelor cazute."""

import time

import pytest

from gamebot.behaviors.loot import LootBehavior
from gamebot.core.config import Profile
from gamebot.tests.conftest import make_frame
from gamebot.tests.test_behaviors import build_ctx


@pytest.fixture
def profil_loot() -> Profile:
    return Profile.from_dict(
        {
            "regions": {"health_bar": {"left": 10, "top": 10, "width": 100, "height": 10}},
            "colors": {
                "health": {"low": [50, 200, 200], "high": [70, 255, 255]},
                # Petele galbene din cadrul sintetic tin loc de etichete de obiect.
                "loot_auriu": {"low": [25, 200, 200], "high": [35, 255, 255]},
            },
            "behaviors": {"loot": True},
            "loot": {
                "colors": ["loot_auriu"],
                "min_area": 100,
                "click_delay": 0.01,
                "interval": 0.0,
            },
        }
    )


def clickuri(ctx):
    """Unde a cazut fiecare click.

    Mutarea mouse-ului e o traiectorie curbata, deci evenimentele "move" sunt
    zeci - noua ne trebuie doar ultima pozitie dinaintea fiecarei apasari.
    """
    tinte, ultima = [], None
    for kind, valoare in ctx.controller.backend.events:
        if kind == "move":
            ultima = valoare
        elif kind == "mouse_down" and ultima is not None:
            tinte.append(ultima)
    return tinte


def test_vede_obiectele_si_le_ridica(profil_loot, tmp_path):
    ctx = build_ctx(profil_loot, make_frame(1.0, nodes=3), tmp_path)
    ctx.refresh()
    behavior = LootBehavior()

    assert behavior.should_run(ctx)
    behavior.run(ctx)

    assert ctx.stats.loots == 3
    assert len(clickuri(ctx)) >= 3


def test_nu_face_nimic_pe_ecran_gol(profil_loot, tmp_path):
    ctx = build_ctx(profil_loot, make_frame(1.0, nodes=0), tmp_path)
    ctx.refresh()
    assert not LootBehavior().should_run(ctx)


def test_da_click_sub_eticheta(profil_loot, tmp_path):
    """Numele obiectului sta deasupra lui; clicul trebuie sa cada pe obiect."""
    profil_loot.raw["loot"]["click_offset_y"] = 20
    ctx = build_ctx(profil_loot, make_frame(1.0, nodes=1), tmp_path)
    ctx.refresh()

    LootBehavior().run(ctx)

    # Petele sunt centrate pe y=215; clicul trebuie sa fie mai jos.
    assert all(y > 225 for _, y in clickuri(ctx))


def test_nu_insista_pe_acelasi_obiect(profil_loot, tmp_path):
    """Un obiect blocat dupa un gard ar tine botul pe loc la nesfarsit."""
    ctx = build_ctx(profil_loot, make_frame(1.0, nodes=2), tmp_path)
    ctx.refresh()
    behavior = LootBehavior()

    behavior.run(ctx)
    ctx.refresh()

    assert behavior._obiecte(ctx) == []


def test_raza_de_adunare_lasa_obiectele_departate(profil_loot, tmp_path):
    """Altfel personajul traverseaza harta dupa un obiect din colt."""
    profil_loot.raw["loot"]["pickup_radius"] = 40
    ctx = build_ctx(profil_loot, make_frame(1.0, nodes=3), tmp_path)
    ctx.refresh()

    assert LootBehavior()._obiecte(ctx) == []


def test_limita_pe_trecere(profil_loot, tmp_path):
    profil_loot.raw["loot"]["max_per_pass"] = 2
    ctx = build_ctx(profil_loot, make_frame(1.0, nodes=3), tmp_path)
    ctx.refresh()

    LootBehavior().run(ctx)

    assert ctx.stats.loots == 2


def test_fara_culori_si_fara_tasta_e_dezactivat(profil_loot, tmp_path):
    profil_loot.raw["loot"]["colors"] = []
    ctx = build_ctx(profil_loot, make_frame(1.0, nodes=2), tmp_path)
    assert not LootBehavior().enabled(ctx)


def test_apasa_tasta_de_ridicare_daca_exista(profil_loot, tmp_path):
    profil_loot.keys["loot"] = "g"
    ctx = build_ctx(profil_loot, make_frame(1.0, nodes=1), tmp_path)
    ctx.refresh()

    LootBehavior().run(ctx)

    apasate = [v for k, v in ctx.controller.backend.events if k == "key_down"]
    assert "g" in apasate


def test_respecta_intervalul_intre_treceri(profil_loot, tmp_path):
    profil_loot.raw["loot"]["interval"] = 30.0
    ctx = build_ctx(profil_loot, make_frame(1.0, nodes=2), tmp_path)
    ctx.refresh()
    behavior = LootBehavior()

    behavior.run(ctx)

    assert not behavior.should_run(ctx)


def test_prioritatea_e_sub_lupta_si_peste_mers(profil_loot, tmp_path):
    from gamebot.behaviors.combat import CombatBehavior
    from gamebot.behaviors.travel import TravelBehavior

    assert CombatBehavior.priority > LootBehavior.priority > TravelBehavior.priority


# ------------------------------------------- culesul din mers, pe langa traseu


def test_raza_se_masoara_de_la_personaj_nu_de_la_centrul_ecranului(profil_loot, tmp_path):
    """Cu jocul intr-o fereastra mutata, cercul trebuie sa il urmeze."""
    from gamebot.core.capture import Region

    ctx = build_ctx(profil_loot, make_frame(1.0, nodes=3), tmp_path)
    ctx.refresh()
    profil_loot.raw["loot"]["pickup_radius"] = 60

    # Obiectele sunt la (55, 215), (115, 215) si (175, 215). Fata de centrul
    # ecranului (200, 150) cel mai apropiat e la ~70 px, deci niciunul nu intra.
    assert LootBehavior()._obiecte(ctx) == []

    # Cu fereastra mutata, personajul ajunge la (120, 215) - langa ele.
    ctx.game_area = Region(0, 130, 240, 170)
    assert len(LootBehavior()._obiecte(ctx)) == 2


def test_redarea_segmentului_cheama_periodic_culesul(test_profile, tmp_path):
    """Fara asta, un segment lung inseamna o tura intreaga fara sa adune nimic."""
    from gamebot.core.input_ctl import InputController
    from gamebot.core.navigation import RoutePlayer
    from gamebot.core.route import InputEvent, Route, Waypoint

    evenimente = [InputEvent("key_down", 0.02, key="w") for _ in range(20)]
    ruta = Route(name="t", waypoints=[Waypoint(0, "travel", events=evenimente)])
    player = RoutePlayer(ruta, InputController(dry_run=True))

    apeluri = []
    player.on_tick = lambda: apeluri.append(1)
    player.tick_interval = 0.05

    player.play_segment(ruta.waypoints[0])

    assert len(apeluri) >= 2, "culesul n-a fost chemat in timpul mersului"


def test_o_actiune_care_crapa_nu_opreste_mersul(test_profile, tmp_path):
    from gamebot.core.input_ctl import InputController
    from gamebot.core.navigation import RoutePlayer
    from gamebot.core.route import InputEvent, Route, Waypoint

    ruta = Route(name="t", waypoints=[
        Waypoint(0, "travel", events=[InputEvent("key_down", 0.01, key="w")] * 5)])
    player = RoutePlayer(ruta, InputController(dry_run=True))
    player.tick_interval = 0.0

    def crapa():
        raise RuntimeError("intentionat")

    player.on_tick = crapa

    assert player.play_segment(ruta.waypoints[0]) is True


def test_mersul_foloseste_aceeasi_instanta_de_cules(profil_loot, tmp_path):
    """Aceeasi lista neagra: un obiect de neluat nu se reincearca la fiecare pas."""
    from gamebot.behaviors.travel import TravelBehavior
    from gamebot.core.input_ctl import InputController
    from gamebot.core.navigation import RoutePlayer
    from gamebot.core.route import Route, Waypoint

    controller = InputController(dry_run=True)
    player = RoutePlayer(Route(name="t", waypoints=[Waypoint(0, "travel")]), controller)
    ctx = build_ctx(profil_loot, make_frame(1.0, nodes=1), tmp_path, player=player)
    ctx.controller = controller

    cules = LootBehavior()
    ctx.behaviors = {"loot": cules}

    TravelBehavior()._pregateste_culesul(ctx, player)

    assert player.on_tick is not None
    player.on_tick()
    assert ctx.stats.loots == 1
    assert len(cules._incercate) == 1, "lista neagra trebuie sa fie a instantei comune"
