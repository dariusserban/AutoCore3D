"""Configurarea inregistrarii. Nu porneste ascultatorii, doar verifica setarile."""

import pytest

from gamebot.core.recorder import DEFAULT_HOTKEYS, RouteRecorder
from gamebot.core.route import InputEvent


def build(tmp_path, **kwargs) -> RouteRecorder:
    return RouteRecorder(name="t", output_dir=tmp_path, **kwargs)


def test_tastele_implicite_acopera_tipurile_de_reper(tmp_path):
    recorder = build(tmp_path)
    assert set(recorder.hotkeys.values()) >= {"portal", "travel", "combat"}
    assert recorder.pause_key == "f9" and recorder.stop_key == "f10"


def test_tastele_pot_fi_schimbate_din_profil(tmp_path):
    """Daca jocul foloseste deja F5, muti marcarea pe alta tasta."""
    recorder = build(tmp_path, hotkeys={"F1": "travel", "F2": "combat"},
                     pause_key="F3", stop_key="F4")

    assert recorder.hotkeys == {"f1": "travel", "f2": "combat"}
    assert recorder.pause_key == "f3"
    assert recorder.stop_key == "f4"


def test_aceeasi_tasta_pentru_reper_si_control_e_respinsa(tmp_path):
    """Altfel ai apasa pentru un reper si ai opri inregistrarea din greseala."""
    with pytest.raises(ValueError, match="f10"):
        build(tmp_path, hotkeys={"f10": "combat"})


def test_marcarea_taie_segmentul_si_il_ataseaza_reperului_anterior(tmp_path):
    recorder = build(tmp_path)

    recorder.mark_waypoint("travel")
    recorder._events = [InputEvent("key_down", 0.5, key="w")]
    recorder.mark_waypoint("combat")

    assert len(recorder.route.waypoints) == 2
    # Evenimentele sunt drumul *catre* reperul nou, deci stau la cel dinainte.
    assert len(recorder.route.waypoints[0].events) == 1
    assert recorder.route.waypoints[1].events == []


def test_primul_reper_se_pune_singur(tmp_path):
    """Cine merge traseul fara sa apese F5 trebuie sa ramana totusi cu ceva."""
    recorder = build(tmp_path)

    reper = recorder.start_recording()

    assert len(recorder.route.waypoints) == 1
    assert reper.kind == "travel" and reper.label == "start"


def test_dupa_pornire_mersul_intra_in_primul_reper(tmp_path):
    recorder = build(tmp_path)
    recorder.start_recording()
    recorder._events = [InputEvent("mouse_down", 0.3, x=500, y=400, button="left")]

    ruta = recorder._finalize()

    assert len(ruta.waypoints) == 1
    assert len(ruta.waypoints[0].events) == 1
    assert (tmp_path / "route.json").exists()


def test_portalul_asteapta_clicul_urmator(tmp_path):
    recorder = build(tmp_path)
    waypoint = recorder.mark_waypoint("portal")

    assert recorder._awaiting_portal is waypoint
    assert waypoint.kind == "portal"


def test_fara_repere_nu_se_salveaza_nimic(tmp_path):
    recorder = build(tmp_path)
    route = recorder._finalize()

    assert route.waypoints == []
    assert not (tmp_path / "route.json").exists()


def test_pauza_de_gandire_nu_intra_in_ruta(tmp_path):
    """Un dt e taiat la 5s: nu vrem sa reproduca o pauza de citit chat-ul."""
    recorder = build(tmp_path)
    recorder._last_event_at = 0.0
    recorder._dt()  # initializeaza ceasul

    import time
    recorder._last_event_at = time.monotonic() - 120
    assert recorder._dt() == 5.0


# ------------------------------------------- oprirea din fereastra salveaza


def test_butonul_de_oprire_salveaza_ruta(tmp_path):
    """OPRESTE trebuie sa faca exact ce face F10, nu sa arunce tura.

    Inainte, butonul doar omora procesul dupa opt secunde: tot ce inregistrasesi
    se pierdea, fara niciun mesaj.
    """
    semnal = tmp_path / ".stop"
    recorder = build(tmp_path / "ruta", stop_file=semnal)
    recorder.start_recording()
    recorder._events = [InputEvent("mouse_down", 0.4, x=100, y=200, button="left")]

    assert recorder.stop_file == semnal

    ruta = recorder._finalize()

    assert len(ruta.waypoints) == 1
    assert (tmp_path / "ruta" / "route.json").exists()


def test_fara_fisier_semnal_nu_se_schimba_nimic(tmp_path):
    assert build(tmp_path).stop_file is None
