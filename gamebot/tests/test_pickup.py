"""Culesul cu tasta: gasirea obiectelor in cerc si lista neagra."""

import time

import pytest

from gamebot.core.config import Profile
from gamebot.core.pickup import Blacklist, culori_din_profil, find_loot
from gamebot.tests.conftest import make_frame

GALBEN = [([25, 200, 200], [35, 255, 255])]
CENTRU = (200, 150)  # centrul cadrului sintetic


def test_gaseste_toate_obiectele_fara_raza():
    assert len(find_loot(make_frame(nodes=3), GALBEN, CENTRU, min_area=100)) == 3


def test_cercul_taie_ce_e_in_afara():
    """Ce se vede in cerc e exact ce se aduna - asta e intelegerea cu ecranul."""
    cadru = make_frame(nodes=3)

    # Mob-urile sunt la (55, 215), (115, 215), (175, 215); centrul e (200, 150).
    departe = find_loot(cadru, GALBEN, CENTRU, radius=50, min_area=100)
    aproape = find_loot(cadru, GALBEN, CENTRU, radius=400, min_area=100)

    assert departe == []
    assert len(aproape) == 3


def test_cele_mai_apropiate_primele():
    """Personajul se deplaseaza cel mai putin daca incepe cu ce e langa el."""
    gasite = find_loot(make_frame(nodes=3), GALBEN, CENTRU, min_area=100)
    distante = [abs(b.center[0] - CENTRU[0]) for b in gasite]
    assert distante == sorted(distante)


def test_offsetul_muta_rezultatele_in_coordonate_de_ecran():
    """Cand cadrul e decupajul unei ferestre, clicurile trebuie sa cada corect."""
    fara = find_loot(make_frame(nodes=1), GALBEN, CENTRU, min_area=100)
    cu = find_loot(make_frame(nodes=1), GALBEN, CENTRU, min_area=100, offset=(950, 102))

    assert cu[0].center[0] == fara[0].center[0] + 950
    assert cu[0].center[1] == fara[0].center[1] + 102


def test_imaginea_goala_nu_arunca():
    import numpy as np

    assert find_loot(np.zeros((0, 0, 3), dtype=np.uint8), GALBEN, CENTRU) == []
    assert find_loot(None, GALBEN, CENTRU) == []


# ------------------------------------------------------------- lista neagra


def test_lista_neagra_retine_si_uita():
    lista = Blacklist(seconds=0.2, distance=30)
    lista.add(100, 100)

    assert lista.contains(105, 105)
    assert not lista.contains(200, 200)

    time.sleep(0.25)
    assert not lista.contains(105, 105)


def test_lista_neagra_scoate_obiectul_din_rezultate():
    cadru = make_frame(nodes=3)
    lista = Blacklist()
    primul = find_loot(cadru, GALBEN, CENTRU, min_area=100)[0]
    lista.add(*primul.center)

    ramase = find_loot(cadru, GALBEN, CENTRU, min_area=100, blacklist=lista)

    assert len(ramase) == 2
    assert primul.center not in [b.center for b in ramase]


def test_golirea_listei():
    lista = Blacklist()
    lista.add(1, 1)
    lista.clear()
    assert not lista.contains(1, 1)


# ---------------------------------------------------------------- culorile


def test_culorile_se_iau_din_profil():
    profil = Profile.from_dict({
        "colors": {
            "loot_auriu": {"low": [18, 110, 120], "high": [32, 255, 255]},
            "loot_verde": {"low": [40, 90, 90], "high": [80, 255, 255]},
        }
    })

    culori = culori_din_profil(profil, ["loot_auriu", "loot_verde"])

    assert len(culori) == 2
    assert culori[0][0] == [18, 110, 120]


def test_culorile_inexistente_se_sar_in_tacere():
    """O culoare scrisa gresit in profil nu trebuie sa opreasca culesul."""
    profil = Profile.from_dict({"colors": {"a": {"low": [0, 0, 0], "high": [1, 1, 1]}}})
    assert len(culori_din_profil(profil, ["a", "inexistenta"])) == 1


def test_profilul_de_dso_are_culori_de_loot():
    from pathlib import Path

    cale = Path(__file__).resolve().parents[1] / "profiles" / "drakensang.yaml"
    profil = Profile.load(cale)
    culori = culori_din_profil(profil, profil.section("loot")["colors"])

    assert len(culori) >= 3, "profilul livrat trebuie sa poata cauta obiecte din prima"


def test_profilul_de_dso_are_setari_de_cules_cu_tasta():
    from pathlib import Path

    cale = Path(__file__).resolve().parents[1] / "profiles" / "drakensang.yaml"
    pickup = Profile.load(cale).section("pickup")

    assert pickup["hotkey"] == "f7"
    assert pickup["radius"] > 0
