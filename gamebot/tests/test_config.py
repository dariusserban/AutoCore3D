"""Incarcarea profilului si avertismentele de configurare."""

from pathlib import Path

import pytest

from gamebot.core.capture import Region
from gamebot.core.config import Profile

PROFIL_EXEMPLU = Path(__file__).resolve().parents[1] / "profiles" / "exemplu.yaml"


def test_profilul_de_exemplu_se_incarca():
    profile = Profile.load(PROFIL_EXEMPLU)

    assert profile.name == "exemplu"
    assert isinstance(profile.region("minimap"), Region)
    assert profile.color("health").low == (40, 80, 70)
    assert profile.key("attack_rotation") == ["1", "2", "3", "4"]
    assert profile.threshold("heal_below", 0.0) == 0.55
    assert profile.enabled("combat")
    assert not profile.enabled("idle_click")


def test_profil_inexistent_da_indicatie_utila(tmp_path):
    with pytest.raises(FileNotFoundError, match="exemplu.yaml"):
        Profile.load(tmp_path / "nu_exista.yaml")


def test_profil_gol_are_valori_implicite():
    profile = Profile.from_dict({})
    assert profile.monitor == 1
    assert profile.region("orice") is None
    assert profile.key("orice", "implicit") == "implicit"
    assert profile.section("inexistenta") == {}


def test_avertismente_pentru_configurare_incompleta():
    profile = Profile.from_dict({"behaviors": {"survival": True, "combat": True, "gather": True}})
    probleme = " ".join(profile.missing_pieces())

    assert "health_bar" in probleme
    assert "attack_rotation" in probleme
    assert "resource_node" in probleme
    assert "minimap" in probleme


def test_profilul_de_exemplu_nu_are_lipsuri_grave():
    """Exemplul livrat trebuie sa fie coerent, ca sa poata fi copiat ca punct de plecare."""
    assert Profile.load(PROFIL_EXEMPLU).missing_pieces() == []


def test_regiunea_converteste_coordonate():
    region = Region(100, 50, 200, 20)
    assert region.right == 300 and region.bottom == 70
    assert region.center == (200, 60)
    assert region.contains(150, 60)
    assert not region.contains(150, 200)
    assert region.to_absolute(10, 5) == (110, 55)


def test_regiunea_din_doua_puncte_normalizeaza_ordinea():
    assert Region.from_points(300, 200, 100, 50) == Region(100, 50, 200, 150)
