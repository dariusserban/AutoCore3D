"""Salvarea si citirea rutei inregistrate."""

import pytest

from gamebot.core.route import InputEvent, Route, Waypoint


def ruta_demo() -> Route:
    return Route(
        name="padure",
        loop=True,
        screen={"width": 1920, "height": 1080},
        waypoints=[
            Waypoint(0, "travel", events=[InputEvent("key_down", 0.0, key="w"),
                                          InputEvent("key_up", 2.5, key="w")]),
            Waypoint(1, "combat", dwell=30.0, events=[InputEvent("move", 0.1, x=500, y=400)]),
            Waypoint(2, "gather", dwell=15.0),
        ],
    )


def test_salvare_si_citire_pastreaza_totul(tmp_path):
    original = ruta_demo()
    original.save(tmp_path)
    incarcata = Route.load(tmp_path)

    assert incarcata.name == original.name
    assert len(incarcata) == 3
    assert incarcata.screen == {"width": 1920, "height": 1080}
    assert incarcata.waypoints[1].kind == "combat"
    assert incarcata.waypoints[1].dwell == 30.0
    assert incarcata.waypoints[0].events[1].key == "w"
    assert incarcata.waypoints[0].events[1].dt == 2.5


def test_evenimentele_nu_pastreaza_campuri_goale():
    """Un eveniment are zeci de mii de frati in fisier; fara campuri inutile.

    O tasta apasata n-are coordonate, iar o miscare de mouse n-are buton -
    daca le-am serializa pe toate ca null, fisierul s-ar dubla degeaba.
    """
    tasta = InputEvent("key_down", 0.4, key="w").as_dict()
    assert tasta == {"kind": "key_down", "dt": 0.4, "key": "w"}

    miscare = InputEvent("move", 0.1, x=500, y=400).as_dict()
    assert "button" not in miscare and "key" not in miscare


def test_bucla_se_intoarce_la_inceput():
    route = ruta_demo()
    assert route.get(3).index == 0
    assert route.next_index(2) == 0


def test_fara_bucla_se_opreste_la_ultimul():
    route = ruta_demo()
    route.loop = False
    assert route.get(99).index == 2
    assert route.next_index(2) == 2


def test_durata_totala_include_stationarea():
    route = ruta_demo()
    # 2.5s de mers + 0.1s + 45s de stationat
    assert route.total_duration == pytest.approx(47.6, abs=0.01)


def test_of_kind_filtreaza():
    assert len(ruta_demo().of_kind("combat")) == 1


def test_ruta_lipsa_da_eroare_explicita(tmp_path):
    with pytest.raises(FileNotFoundError, match="Inregistreaza"):
        Route.load(tmp_path / "nu_exista")


def test_ruta_goala_nu_poate_fi_parcursa():
    with pytest.raises(IndexError):
        Route(name="goala").get(0)


def test_describe_e_lizibil():
    text = ruta_demo().describe()
    assert "3 repere" in text and "combat:1" in text
