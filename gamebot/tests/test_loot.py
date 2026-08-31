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
