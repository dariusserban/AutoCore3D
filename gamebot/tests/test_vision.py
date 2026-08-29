"""Citirea pixelilor: bare, sabloane, pete de culoare."""

import numpy as np
import pytest

from gamebot.core import vision
from gamebot.tests.conftest import make_frame


def bara(ratio: float, width: int = 200, height: int = 12) -> np.ndarray:
    """Bara verde umpluta pana la `ratio` din latime, pe fundal inchis."""
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, : int(width * ratio)] = (0, 255, 0)
    return image


VERDE = ([50, 200, 200], [70, 255, 255])


@pytest.mark.parametrize("ratio", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_bar_fill_ratio_citeste_corect(ratio):
    masurat = vision.bar_fill_ratio(bara(ratio), *VERDE)
    assert abs(masurat - ratio) < 0.02


def test_bar_fill_ratio_ignora_pixeli_razleti():
    """Un pixel colorat la capatul barei nu trebuie sa o dea plina."""
    image = bara(0.3)
    image[6, 190] = (0, 255, 0)  # un singur pixel, departe de zona plina
    assert vision.bar_fill_ratio(image, *VERDE) < 0.4


def test_bar_fill_ratio_pe_imagine_goala():
    assert vision.bar_fill_ratio(np.zeros((10, 10, 3), dtype=np.uint8), *VERDE) == 0.0


def test_find_template_gaseste_pozitia_exacta():
    frame = make_frame(nodes=1)
    needle = frame[200:230, 40:70].copy()
    match = vision.find_template(frame, needle, threshold=0.9)
    assert match is not None
    assert (match.x, match.y) == (40, 200)
    assert match.score > 0.99


def test_find_template_refuza_sub_prag():
    """Un sablon care nu apare pe ecran nu trebuie raportat ca gasit."""
    frame = make_frame(nodes=1)
    needle = np.random.default_rng(99).integers(0, 255, (20, 20, 3), dtype=np.uint8)
    assert vision.find_template(frame, needle, threshold=0.95) is None


def test_find_template_cu_sablon_mai_mare_decat_ecranul():
    small = np.zeros((10, 10, 3), dtype=np.uint8)
    big = np.zeros((50, 50, 3), dtype=np.uint8)
    assert vision.find_template(small, big) is None


def test_find_all_templates_nu_raporteaza_dubluri():
    """Trei noduri identice trebuie sa dea exact trei potriviri, nu zeci."""
    frame = make_frame(nodes=3)
    needle = frame[200:230, 40:70].copy()
    matches = vision.find_all_templates(frame, needle, threshold=0.95)
    assert len(matches) == 3


def test_color_blobs_numara_obiectele():
    frame = make_frame(nodes=3)
    blobs = vision.color_blobs(frame, [25, 200, 200], [35, 255, 255], min_area=100)
    assert len(blobs) == 3
    # Fiecare pata are ~30x30 px si trebuie sa fie in jumatatea de jos a imaginii.
    assert all(b.y > 150 for b in blobs)


def test_color_blobs_filtreaza_dupa_arie():
    frame = make_frame(nodes=2)
    assert vision.color_blobs(frame, [25, 200, 200], [35, 255, 255], min_area=5000) == []


def test_similarity_identice_si_diferite():
    a = make_frame(nodes=2)
    b = make_frame(nodes=2)
    assert vision.similarity(a, b) > 0.99
    assert vision.similarity(a, make_frame(nodes=0)) < 0.99


def test_frames_differ_detecteaza_schimbarea():
    a = make_frame(1.0)
    assert not vision.frames_differ(a, a.copy())
    assert vision.frames_differ(a, make_frame(0.1, nodes=3))


def test_template_library_lipsa_da_eroare_clara(tmp_path):
    lib = vision.TemplateLibrary(tmp_path)
    assert not lib.has("inexistent")
    with pytest.raises(KeyError, match="inexistent"):
        lib["inexistent"]
