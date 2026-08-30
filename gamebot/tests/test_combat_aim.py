"""Modul de lupta pentru ARPG-uri izometrice (click-to-move, fara tinta)."""

import pytest

from gamebot.behaviors.combat import CombatBehavior
from gamebot.core.config import Profile
from gamebot.core.route import Waypoint
from gamebot.tests.conftest import make_frame
from gamebot.tests.test_behaviors import build_ctx


@pytest.fixture
def profil_arpg() -> Profile:
    """Profil in stilul Drakensang: click-to-move, lupta prin tintire."""
    return Profile.from_dict(
        {
            "name": "arpg",
            "regions": {
                "health_bar": {"left": 10, "top": 10, "width": 100, "height": 10},
                "minimap": {"left": 300, "top": 0, "width": 100, "height": 100},
            },
            "colors": {
                "health": {"low": [50, 200, 200], "high": [70, 255, 255]},
                # Nodurile galbene din cadrul sintetic tin loc de mob-uri.
                "mob": {"low": [25, 200, 200], "high": [35, 255, 255]},
            },
            "keys": {"heal": "5"},
            "thresholds": {"heal_below": 0.5},
            "behaviors": {"combat": True},
            "input": {"movement": "click"},
            "combat": {
                "mode": "aim",
                "anywhere": True,
                "enemy_color": "mob",
                "enemy_min_area": 100,
                "max_fight_seconds": 0.05,
                "global_cooldown": 0.01,
                "approach_seconds": 0.0,
                "abilities": [{"key": "1", "cooldown": 0.0}],
            },
        }
    )


def evenimente(ctx, tip):
    return [value for kind, value in ctx.controller.backend.events if kind == tip]


def test_intra_in_lupta_cand_vede_mob_uri(profil_arpg, tmp_path):
    ctx = build_ctx(profil_arpg, make_frame(1.0, nodes=3), tmp_path)
    ctx.refresh()
    assert CombatBehavior().should_run(ctx)


def test_nu_intra_daca_ecranul_e_gol(profil_arpg, tmp_path):
    ctx = build_ctx(profil_arpg, make_frame(1.0, nodes=0), tmp_path)
    ctx.refresh()
    assert not CombatBehavior().should_run(ctx)


def test_nu_are_nevoie_de_bara_de_tinta(profil_arpg, tmp_path):
    """Profilul ARPG nici nu defineste target_health_bar, si totusi lupta."""
    ctx = build_ctx(profil_arpg, make_frame(1.0, nodes=2), tmp_path)
    ctx.refresh()

    assert not ctx.has_target()
    assert CombatBehavior().should_run(ctx)


def test_duce_cursorul_pe_mob_si_apasa_abilitatea(profil_arpg, tmp_path):
    ctx = build_ctx(profil_arpg, make_frame(1.0, nodes=3), tmp_path)
    ctx.refresh()

    CombatBehavior().run(ctx)

    assert "1" in evenimente(ctx, "key_down")
    # Cursorul trebuie sa ajunga in zona mob-urilor (y in jur de 215).
    pozitii = evenimente(ctx, "move")
    assert pozitii, "nu a miscat deloc cursorul"
    assert any(190 < y < 240 for _, y in pozitii)


def test_tinteste_centrul_gramezii_nu_un_singur_mob(profil_arpg, tmp_path):
    """Cu abilitati in zona, centrul grupului prinde mai multi mobi deodata."""
    ctx = build_ctx(profil_arpg, make_frame(1.0, nodes=3), tmp_path)
    ctx.refresh()
    enemies = CombatBehavior._enemies(ctx)

    tinta = CombatBehavior._pick_cluster(ctx, enemies, radius=200)

    # Mob-urile sunt la x=55, 115, 175; centrul lor e ~115.
    assert 100 < tinta[0] < 135


def test_raza_mica_tinteste_doar_mobul_cel_mai_apropiat(profil_arpg, tmp_path):
    ctx = build_ctx(profil_arpg, make_frame(1.0, nodes=3), tmp_path)
    ctx.refresh()
    enemies = CombatBehavior._enemies(ctx)

    tinta = CombatBehavior._pick_cluster(ctx, enemies, radius=10)

    # Centrul ecranului e la x=200, deci cel mai apropiat mob e cel de la 175.
    assert 160 < tinta[0] < 190


def test_lupta_cere_resincronizare(profil_arpg, tmp_path):
    ctx = build_ctx(profil_arpg, make_frame(1.0, nodes=2), tmp_path)
    ctx.refresh()

    CombatBehavior().run(ctx)

    assert ctx.needs_resync


def test_se_opreste_cand_viata_scade(profil_arpg, tmp_path):
    """Sub pragul de vindecare iese din lupta si lasa supravietuirea sa preia."""
    ctx = build_ctx(profil_arpg, make_frame(0.2, nodes=3), tmp_path)
    ctx.refresh()

    CombatBehavior().run(ctx)

    assert "1" not in evenimente(ctx, "key_down")


def test_apropierea_prin_click_merge_spre_mob_nu_pe_el(profil_arpg, tmp_path):
    """La click-to-move dam click pe drum, ca sa nu declansam atacul de departe."""
    ctx = build_ctx(profil_arpg, make_frame(1.0, nodes=1), tmp_path)
    ctx.refresh()
    behavior = CombatBehavior()

    behavior._walk_towards(ctx, (100, 260), fraction=0.5)

    cx, cy = ctx.screen_center()
    ultima = evenimente(ctx, "move")[-1]
    # Clicul cade la jumatatea drumului dintre personaj (centru) si mob.
    assert abs(ultima[0] - (cx + 100) // 2) < 6
    assert abs(ultima[1] - (cy + 260) // 2) < 6


def test_fara_taste_de_directie_apropierea_pe_tastatura_nu_apasa_nimic(profil_arpg, tmp_path):
    """Profilul ARPG are keys.forward gol; nu trebuie sa iasa o apasare goala."""
    profil_arpg.raw["input"]["movement"] = "keyboard"
    profil_arpg.keys["forward"] = ""
    ctx = build_ctx(profil_arpg, make_frame(1.0, nodes=1), tmp_path)
    ctx.refresh()

    CombatBehavior()._approach(ctx, 0.01, target=(100, 260))

    assert evenimente(ctx, "key_down") == []
