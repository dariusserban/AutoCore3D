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
    profile = Profile.from_dict({
        "behaviors": {"survival": True, "combat": True, "gather": True, "loot": True}
    })
    probleme = " ".join(profile.missing_pieces())

    assert "health_bar" in probleme
    assert "attack_rotation" in probleme
    assert "resource_node" in probleme
    assert "loot" in probleme


def test_minimapa_lipsa_nu_mai_e_o_problema():
    """Fara minimapa, ancorele se iau din tot ecranul - e varianta implicita."""
    profile = Profile.from_dict({"behaviors": {}})
    assert "minimap" not in " ".join(profile.missing_pieces())


def test_regiune_procentuala_se_rezolva_dupa_fereastra():
    profile = Profile.from_dict({"regions": {"bara": {"rel": [0.5, 0.9, 0.1, 0.02]}}})

    assert profile.has_region("bara")
    assert profile.region("bara") is None  # nelegata inca de nicio fereastra

    profile.bind_window(Region(0, 0, 1000, 500))

    assert profile.region("bara") == Region(500, 450, 100, 10)


def test_aceeasi_regiune_da_alti_pixeli_la_alta_rezolutie():
    """Asta e tot rostul procentelor: sa nu se recalibreze nimic."""
    def rezolva(latime, inaltime):
        p = Profile.from_dict({"regions": {"b": {"rel": [0.1, 0.1, 0.5, 0.5]}}})
        p.bind_window(Region(0, 0, latime, inaltime))
        return p.region("b")

    assert rezolva(1920, 1080) == Region(192, 108, 960, 540)
    assert rezolva(2560, 1440) == Region(256, 144, 1280, 720)


def test_regiunile_in_pixeli_raman_neatinse_de_fereastra():
    profile = Profile.from_dict({"regions": {"fix": {"left": 5, "top": 6, "width": 7, "height": 8}}})
    profile.bind_window(Region(0, 0, 3000, 2000))
    assert profile.region("fix") == Region(5, 6, 7, 8)


def test_titlul_ferestrei_din_profil():
    assert Profile.from_dict({"window": {"title": "Drakensang"}}).window_title == "Drakensang"
    assert Profile.from_dict({}).window_title == ""


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


def test_profilul_de_dso_nu_urmareste_viata():
    """Cerut explicit: nimic legat de viata in profilul de Drakensang.

    Botul nu trebuie sa se uite la bara de viata, sa se vindece sau sa se
    opreasca din cauza ei - a fost sursa a doua opriri false si nu aduce nimic
    cand jucatorul isi gestioneaza singur potiunile.
    """
    profile = Profile.load(PROFIL_EXEMPLU.parent / "drakensang.yaml")

    assert not profile.enabled("survival")
    assert not profile.has_region("health_bar")
    assert profile.color("health") is None
    assert not profile.key("heal")
    assert "heal_below" not in profile.thresholds
    assert profile.section("survival") == {}
    assert profile.missing_pieces() == []
