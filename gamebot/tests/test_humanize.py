"""Variatia trebuie sa fie variata, dar marginita."""

import math

from gamebot.core import humanize


def test_delay_ramane_in_limite():
    values = [humanize.delay(0.25) for _ in range(500)]
    assert all(0.25 * 0.4 <= v <= 0.25 * 3.0 for v in values)
    # Media trebuie sa fie in jurul valorii cerute, nu sistematic deplasata.
    assert 0.2 < sum(values) / len(values) < 0.35


def test_delay_nu_repeta_aceeasi_valoare():
    values = {round(humanize.delay(0.3), 6) for _ in range(50)}
    assert len(values) > 45, "intarzierile ies prea des identice"


def test_jitter_point_ramane_in_raza():
    for _ in range(300):
        x, y = humanize.jitter_point(100, 100, 5)
        assert math.hypot(x - 100, y - 100) <= 5 + 1  # +1 pentru rotunjire


def test_jitter_point_cu_raza_zero_nu_muta_nimic():
    assert humanize.jitter_point(42, 7, 0) == (42, 7)


def test_mouse_path_ajunge_exact_pe_tinta():
    path = humanize.mouse_path((0, 0), (300, 200))
    assert path[-1] == (300, 200)
    assert len(path) > 5


def test_mouse_path_nu_e_linie_dreapta():
    """Traiectoria trebuie sa se abata de la segmentul direct."""
    start, end = (0, 0), (400, 0)
    path = humanize.mouse_path(start, end, curvature=0.2)
    max_abatere = max(abs(y) for _, y in path)
    assert max_abatere > 5, "traiectoria e perfect dreapta"


def test_mouse_path_distanta_mica_sare_direct():
    assert humanize.mouse_path((10, 10), (11, 10)) == [(11, 10)]


def test_hold_time_peste_pragul_minim():
    assert all(humanize.hold_time() >= 0.03 for _ in range(200))


def test_break_schedule_da_valori_in_interval():
    schedule = humanize.break_schedule((10, 20), (1, 2))
    for _ in range(20):
        work, pause = next(schedule)
        assert 600 <= work <= 1200
        assert 60 <= pause <= 120


def test_seed_face_rularea_reproductibila():
    humanize.seed(7)
    first = [humanize.delay(0.2) for _ in range(10)]
    humanize.seed(7)
    assert first == [humanize.delay(0.2) for _ in range(10)]
    humanize.seed(None)
