"""Urcatul pe montura intre zonele de farmat."""

import time

from gamebot.behaviors.mount import MountBehavior
from gamebot.tests.conftest import make_frame
from gamebot.tests.test_behaviors import build_ctx


def pregateste(profil, tmp_path, **frame_kwargs):
    profil.keys["mount"] = "y"
    profil.behaviors["mount"] = True
    profil.raw["combat"] = {"enemy_color": "resource_node", "enemy_min_area": 100}
    ctx = build_ctx(profil, make_frame(**frame_kwargs), tmp_path)
    ctx.refresh()
    return ctx


def test_fara_tasta_de_montura_comportamentul_e_inactiv(test_profile, tmp_path):
    test_profile.behaviors["mount"] = True
    test_profile.keys["mount"] = ""
    ctx = build_ctx(test_profile, make_frame(), tmp_path)
    assert not MountBehavior().enabled(ctx)


def test_urca_pe_drum_cand_e_liber(test_profile, tmp_path):
    ctx = pregateste(test_profile, tmp_path, nodes=0)
    behavior = MountBehavior()

    assert behavior.should_run(ctx)
    behavior.run(ctx)

    apasate = [v for k, v in ctx.controller.backend.events if k == "key_down"]
    assert "y" in apasate


def test_nu_urca_daca_are_mobi_langa(test_profile, tmp_path):
    """Intai se rezolva lupta; in multe jocuri urcarea oricum s-ar intrerupe."""
    ctx = pregateste(test_profile, tmp_path, nodes=3)
    assert not MountBehavior().should_run(ctx)


def test_nu_urca_cand_stationeaza_intr_o_zona_de_farmat(test_profile, tmp_path):
    ctx = pregateste(test_profile, tmp_path, nodes=0)
    ctx.dwell_until = time.monotonic() + 30
    assert not MountBehavior().should_run(ctx)


def test_nu_spameaza_tasta(test_profile, tmp_path):
    ctx = pregateste(test_profile, tmp_path, nodes=0)
    test_profile.raw["mount"] = {"retry_seconds": 30, "cast_seconds": 0.01}
    behavior = MountBehavior()

    behavior.run(ctx)

    assert not behavior.should_run(ctx)
