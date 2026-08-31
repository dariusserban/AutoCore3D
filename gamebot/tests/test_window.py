"""Gasirea ferestrei jocului si regiunile exprimate in procente."""

import platform

import pytest

from gamebot.core.capture import Region
from gamebot.core.window import WindowInfo, find_window, list_windows, relative_region


def test_procentele_devin_pixeli():
    fereastra = Region(0, 0, 1920, 1080)
    assert relative_region(fereastra, (0.0, 0.0, 1.0, 1.0)) == fereastra
    assert relative_region(fereastra, (0.5, 0.5, 0.25, 0.1)) == Region(960, 540, 480, 108)


def test_pozitia_ferestrei_se_aduna_la_rezultat():
    """Fereastra nu e mereu in coltul ecranului."""
    fereastra = Region(950, 102, 890, 640)
    regiune = relative_region(fereastra, (0.0, 0.0, 0.5, 0.5))

    assert regiune.left == 950 and regiune.top == 102
    assert regiune.width == 445 and regiune.height == 320


def test_regiunea_nu_iese_niciodata_zero():
    """O fractie mica tot trebuie sa dea macar un pixel, nu o regiune goala."""
    regiune = relative_region(Region(0, 0, 100, 100), (0.5, 0.5, 0.0001, 0.0001))
    assert regiune.width >= 1 and regiune.height >= 1


def test_fereastra_minimizata_nu_e_buna():
    mica = WindowInfo("joc", Region(0, 0, 160, 40))
    mare = WindowInfo("joc", Region(0, 0, 1920, 1080))

    assert not mica.is_reasonable
    assert mare.is_reasonable


def test_fara_titlu_nu_cautam_nimic():
    assert find_window("") is None


@pytest.mark.skipif(platform.system() == "Windows", reason="test pentru celelalte sisteme")
def test_pe_alt_sistem_lista_e_goala_nu_o_eroare():
    """Testele trebuie sa treaca si pe masinile fara Windows."""
    assert find_window("orice") is None
    assert list_windows() == []
