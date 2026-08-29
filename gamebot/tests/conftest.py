"""Fixture-uri comune. Toate testele ruleaza fara ecran si fara joc pornit."""

import sys
from pathlib import Path

import numpy as np
import pytest

# Testele ruleaza din radacina repo-ului, importand pachetul `gamebot`.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gamebot.core.capture import ReplayCapture  # noqa: E402
from gamebot.core.config import Profile  # noqa: E402


SCREEN_W, SCREEN_H = 400, 300


def make_frame(health_ratio: float = 1.0, nodes: int = 0, target: bool = False) -> np.ndarray:
    """Construieste un ecran fals cu barele si petele cerute.

    Fundalul are textura (zgomot determinist), nu negru uniform: corelatia
    normalizata folosita la template matching e degenerata pe suprafete plate,
    deci un ecran uniform ar face testele sa treaca sau sa pice din motive care
    nu au legatura cu logica noastra.
    """
    rng = np.random.default_rng(1234)
    frame = rng.integers(20, 60, size=(SCREEN_H, SCREEN_W, 3), dtype=np.uint8)

    # Bara de viata: verde pur (BGR), la (10, 10), 100x10 px.
    filled = int(100 * health_ratio)
    if filled > 0:
        frame[10:20, 10 : 10 + filled] = (0, 255, 0)

    # Bara tintei: la (200, 10), aceeasi culoare.
    if target:
        frame[10:20, 200:280] = (0, 255, 0)

    # Noduri de resurse: patrate galbene cu un miez mai inchis, ca sa aiba
    # structura interna si sa poata fi cautate ca sablon.
    for i in range(nodes):
        x = 40 + i * 60
        frame[200:230, x : x + 30] = (0, 220, 220)
        frame[210:220, x + 10 : x + 20] = (0, 120, 120)

    return frame


@pytest.fixture
def test_profile() -> Profile:
    return Profile.from_dict(
        {
            "name": "test",
            "regions": {
                "health_bar": {"left": 10, "top": 10, "width": 100, "height": 10},
                "target_health_bar": {"left": 200, "top": 10, "width": 80, "height": 10},
                "minimap": {"left": 300, "top": 0, "width": 100, "height": 100},
            },
            "colors": {
                "health": {"low": [50, 200, 200], "high": [70, 255, 255]},
                "resource_node": {"low": [25, 200, 200], "high": [35, 255, 255]},
            },
            "keys": {"heal": "5", "attack_rotation": ["1", "2"], "forward": "w"},
            "thresholds": {"heal_below": 0.5, "flee_below": 0.15},
            "behaviors": {"survival": True, "combat": False, "gather": True, "travel": False},
            "gather": {"anywhere": True, "cast_seconds": 0.01, "click_delay": 0.01},
            "survival": {"heal_cooldown": 0.0},
        }
    )


@pytest.fixture
def frames_full_health():
    return ReplayCapture([make_frame(1.0)])
