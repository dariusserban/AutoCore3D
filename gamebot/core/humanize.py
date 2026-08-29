"""Temporizare si traiectorii cu variatie naturala.

Un bot care apasa o tasta la exact 250 ms distanta, de 4000 de ori la rand, se
comporta diferit de un om nu pentru ca e rapid, ci pentru ca e *constant*.
Modulul asta introduce variatia pe care o are orice mana de om: intarzieri cu
coada la dreapta, curburi in miscarea mouse-ului, pauze scurte cand te uiti in
alta parte.

Scopul e ca botul sa se comporte firesc si sa nu se auto-detecteze prin
regularitate, nu sa ascunda ceva de un sistem anti-cheat.
"""

from __future__ import annotations

import math
import random
import time
from typing import Iterator, Sequence

# Un generator dedicat, ca sa nu depindem de starea globala a lui random si sa
# putem reproduce o sesiune la depanare cu seed().
_rng = random.Random()


def seed(value: int | None) -> None:
    """Fixeaza generatorul, util cand vrei sa reproduci exact o rulare."""
    _rng.seed(value)


def delay(base: float, spread: float = 0.25) -> float:
    """Intoarce o durata in jurul lui `base`, cu coada spre valori mari.

    Distributia lognormala imita bine timpii de reactie umani: majoritatea
    apasarilor sunt aproape de medie, dar din cand in cand una intarzie
    vizibil. `spread` e deviatia relativa (0.25 = ~25%).
    """
    if base <= 0:
        return 0.0
    sigma = max(0.01, spread)
    # mu ales astfel incat mediana distributiei sa cada exact pe `base`.
    value = _rng.lognormvariate(math.log(base), sigma)
    # Taiem cozile extreme: nimeni nu asteapta de 5x mai mult intre doua clicuri.
    return max(base * 0.4, min(value, base * 3.0))


def sleep(base: float, spread: float = 0.25) -> float:
    """Doarme o durata umanizata si intoarce cat a dormit efectiv."""
    waited = delay(base, spread)
    time.sleep(waited)
    return waited


def jitter(value: float, amount: float) -> float:
    """Deplaseaza `value` cu pana la +/- `amount`, uniform."""
    return value + _rng.uniform(-amount, amount)


def jitter_point(x: int, y: int, radius: int) -> tuple[int, int]:
    """Alege un punct aleator in discul de raza `radius` in jurul tintei.

    Clicurile umane nu cad niciodata de doua ori pe acelasi pixel. Folosim
    distributie uniforma pe disc (de aici sqrt-ul), nu pe raza, ca sa nu se
    aglomereze artificial in centru.
    """
    if radius <= 0:
        return x, y
    angle = _rng.uniform(0, 2 * math.pi)
    dist = radius * math.sqrt(_rng.random())
    return int(round(x + dist * math.cos(angle))), int(round(y + dist * math.sin(angle)))


def _cubic_bezier(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    u = 1 - t
    x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
    y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
    return x, y


def _ease(t: float) -> float:
    """Accelerare la plecare, franare la sosire (smoothstep)."""
    return t * t * (3 - 2 * t)


def mouse_path(
    start: tuple[int, int],
    end: tuple[int, int],
    curvature: float = 0.18,
    min_steps: int = 8,
    max_steps: int = 60,
) -> list[tuple[int, int]]:
    """Construieste o traiectorie curbata intre doua puncte.

    Mana nu merge pe linie dreapta si nici cu viteza constanta: pleaca incet,
    accelereaza, franeaza langa tinta. Punctele de control ale curbei sunt
    trase perpendicular pe directia de mers, cu o marime proportionala cu
    distanta, ca miscarile scurte sa nu iasa absurd de arcuite.
    """
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    distance = math.hypot(dx, dy)
    if distance < 2:
        return [(int(ex), int(ey))]

    steps = int(min(max_steps, max(min_steps, distance / 12)))

    # Normala pe segmentul start-end, folosita pentru a impinge curba lateral.
    nx, ny = -dy / distance, dx / distance
    offset = distance * curvature
    side = _rng.choice((-1.0, 1.0))

    c1 = (
        sx + dx * 0.3 + nx * offset * side * _rng.uniform(0.5, 1.0),
        sy + dy * 0.3 + ny * offset * side * _rng.uniform(0.5, 1.0),
    )
    c2 = (
        sx + dx * 0.7 + nx * offset * side * _rng.uniform(0.2, 0.8),
        sy + dy * 0.7 + ny * offset * side * _rng.uniform(0.2, 0.8),
    )

    points: list[tuple[int, int]] = []
    for i in range(1, steps + 1):
        t = _ease(i / steps)
        x, y = _cubic_bezier(start, c1, c2, end, t)
        points.append((int(round(x)), int(round(y))))

    # Ultimul punct trebuie sa fie exact tinta, altfel clicul cade alaturi.
    points[-1] = (int(ex), int(ey))
    return points


def hold_time(base: float = 0.06) -> float:
    """Cat timp sta o tasta apasata. Sub 30 ms multe jocuri pierd apasarea."""
    return max(0.03, delay(base, 0.35))


def should_micro_pause(probability: float = 0.04) -> bool:
    """Din cand in cand un om se opreste o secunda: se uita in chat, bea apa."""
    return _rng.random() < probability


def micro_pause() -> float:
    """O pauza scurta, de genul celei dintre doua actiuni cand esti distras."""
    return sleep(_rng.uniform(0.8, 3.5), 0.2)


def pick(sequence: Sequence):
    """Alegere aleatoare dintr-o secventa, folosind generatorul modulului."""
    return _rng.choice(list(sequence))


def chance(probability: float) -> bool:
    return _rng.random() < probability


def shuffled(sequence: Sequence) -> list:
    items = list(sequence)
    _rng.shuffle(items)
    return items


def break_schedule(
    work_minutes: tuple[float, float] = (25.0, 55.0),
    break_minutes: tuple[float, float] = (2.0, 9.0),
) -> Iterator[tuple[float, float]]:
    """Genereaza perechi (durata de lucru, durata de pauza), in secunde.

    O sesiune de 9 ore fara nicio pauza nu seamana cu joc uman, indiferent cat
    de bine e randomizat restul. Programul asta rupe rularea in intervale.
    """
    while True:
        yield (
            _rng.uniform(*work_minutes) * 60.0,
            _rng.uniform(*break_minutes) * 60.0,
        )
