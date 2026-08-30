"""Deducerea rotatiei de abilitati din luptele inregistrate."""

import random

import pytest

from gamebot.core import learning
from gamebot.core.route import InputEvent, Route, Waypoint


def lupta_simulata(cooldowns: dict[str, float], durata: float = 300.0, seed: int = 7) -> Waypoint:
    """Un segment de lupta in care fiecare tasta e apasata la cooldown-ul ei.

    Apasarile nu cad exact pe cooldown - un om reactioneaza cu intarziere - deci
    adaugam intre 0 si 35% peste, ca in realitate.
    """
    rng = random.Random(seed)
    apasari = []
    for key, cooldown in cooldowns.items():
        moment = 0.0
        while moment < durata:
            moment += cooldown * rng.uniform(1.0, 1.35)
            apasari.append((moment, key))
    apasari.sort()

    events, anterior = [], 0.0
    for moment, key in apasari:
        events.append(InputEvent("key_down", round(moment - anterior, 3), key=key))
        anterior = moment
    return Waypoint(0, "combat", events=events)


def test_recunoaste_cooldown_urile_reale():
    """Cel mai scurt interval la care ai reapasat tasta aproximeaza cooldown-ul."""
    route = Route(name="t", waypoints=[lupta_simulata({"1": 1.5, "2": 6.0, "3": 12.0})])

    rotation = learning.analyze(route)
    dupa_tasta = {a.key: a for a in rotation.abilities}

    assert dupa_tasta["1"].cooldown == pytest.approx(1.5, abs=0.5)
    assert dupa_tasta["2"].cooldown == pytest.approx(6.0, abs=1.0)
    assert dupa_tasta["3"].cooldown == pytest.approx(12.0, abs=1.5)


def test_ordinea_pune_abilitatile_grele_primele():
    route = Route(name="t", waypoints=[lupta_simulata({"1": 1.5, "2": 6.0, "3": 12.0})])
    assert learning.analyze(route).keys == ["3", "2", "1"]


def test_tastele_de_mers_nu_sunt_abilitati():
    route = Route(name="t", waypoints=[lupta_simulata({"1": 1.5, "w": 2.0, "space": 5.0})])
    assert learning.analyze(route).keys == ["1"]


def test_tastele_cu_alt_rost_pot_fi_excluse():
    """Vindecarea se apasa in lupta, dar nu e o abilitate de atac."""
    route = Route(name="t", waypoints=[lupta_simulata({"1": 1.5, "5": 30.0})])

    assert "5" in learning.analyze(route).keys
    assert "5" not in learning.analyze(route, exclude=["5"]).keys


def test_tastele_apasate_o_data_sau_de_doua_ori_se_ignora():
    waypoint = lupta_simulata({"1": 1.5})
    waypoint.events.append(InputEvent("key_down", 1.0, key="p"))
    waypoint.events.append(InputEvent("key_down", 5.0, key="p"))
    route = Route(name="t", waypoints=[waypoint])

    assert "p" not in learning.analyze(route).keys


def test_doar_segmentele_de_lupta_conteaza():
    drum = lupta_simulata({"8": 2.0})
    drum.kind = "travel"
    lupta = lupta_simulata({"1": 1.5}, seed=3)
    lupta.index = 1
    route = Route(name="t", waypoints=[drum, lupta])

    rotation = learning.analyze(route)

    assert rotation.keys == ["1"]
    assert rotation.segments == 1
    # Cu --include-travel intra si drumul in analiza.
    assert set(learning.analyze(route, kinds=("combat", "travel")).keys) == {"1", "8"}


def test_ruta_fara_lupte_nu_da_eroare():
    route = Route(name="goala", waypoints=[Waypoint(0, "travel")])
    rotation = learning.analyze(route)

    assert rotation.abilities == []
    assert "Nu am gasit" in rotation.describe()


def test_sectiunea_de_profil_e_gata_de_lipit():
    route = Route(name="t", waypoints=[lupta_simulata({"1": 1.5, "3": 12.0})])
    section = learning.analyze(route).as_profile_section()

    assert [a["key"] for a in section["abilities"]] == ["3", "1"]
    assert all("cooldown" in a for a in section["abilities"])
    assert section["global_cooldown"] > 0


def test_global_cooldown_e_intervalul_tipic_intre_apasari():
    route = Route(name="t", waypoints=[lupta_simulata({"1": 1.5, "2": 6.0})])
    # Cu o abilitate la 1.5s si una la 6s, intervalul median intre doua apasari
    # de orice fel e putin sub 1.5s.
    assert 0.7 < learning.analyze(route).global_cooldown < 1.8
