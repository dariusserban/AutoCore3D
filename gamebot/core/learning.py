"""Deduce rotatia de abilitati din felul in care te-ai luptat tu.

Cand inregistrezi traseul, fiecare tasta apasata intra in ruta cu momentul ei.
Modulul asta se uita la segmentele de lupta si raspunde la trei intrebari:

  - ce taste sunt abilitati (si nu mers, sarit sau vorbit in chat)?
  - cat de des poate fi apasata fiecare (adica ce cooldown are)?
  - in ce ordine merita folosite?

Estimarea cooldown-ului e partea interesanta. Nu putem citi cooldown-ul din
joc, dar avem ceva aproape la fel de bun: cel mai scurt interval la care ai
reusit tu sa reapesi tasta. Daca ai apasat "3" de 40 de ori si cel mai devreme
ai reusit dupa 11.8 secunde, cooldown-ul e aproape sigur ~12s. Luam percentila
15 a intervalelor, nu minimul absolut, ca o singura apasare dubla din greseala
sa nu strice estimarea.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from typing import Iterable, Optional

from .route import Route, Waypoint

log = logging.getLogger(__name__)

# Taste care aproape sigur nu sunt abilitati. Restul le judecam dupa cum au
# fost folosite.
MOVEMENT_KEYS = {"w", "a", "s", "d", "space", "shift", "ctrl", "ctrl_l", "ctrl_r",
                 "shift_l", "shift_r", "alt", "alt_l", "alt_r", "q", "e"}
CHAT_KEYS = {"enter", "esc", "escape", "tab", "backspace", "f9", "f10", "f11", "f12"}


@dataclass
class Ability:
    """O tasta folosita in lupta, cu ce am dedus despre ea."""

    key: str
    presses: int
    cooldown: float
    share: float  # ce fractiune din apasarile de abilitati reprezinta

    def as_dict(self) -> dict:
        return {"key": self.key, "cooldown": round(self.cooldown, 1)}


@dataclass
class Rotation:
    """Rezultatul analizei: ce abilitati ai folosit si cum."""

    abilities: list[Ability]
    global_cooldown: float
    fight_seconds: float
    segments: int

    @property
    def keys(self) -> list[str]:
        return [a.key for a in self.abilities]

    def as_profile_section(self) -> dict:
        """Bucata de profil care poate fi lipita direct in YAML."""
        return {
            "abilities": [a.as_dict() for a in self.abilities],
            "global_cooldown": round(self.global_cooldown, 2),
        }

    def describe(self) -> str:
        if not self.abilities:
            return "Nu am gasit apasari de abilitati in segmentele de lupta."
        lines = [
            f"Analizate {self.segments} segmente de lupta, {self.fight_seconds/60:.1f} minute.",
            f"Timp intre doua abilitati (global cooldown): {self.global_cooldown:.2f}s",
            "",
            f"  {'tasta':<8} {'apasari':>8} {'cooldown':>10} {'pondere':>9}",
        ]
        for ability in self.abilities:
            lines.append(
                f"  {ability.key:<8} {ability.presses:>8} {ability.cooldown:>9.1f}s "
                f"{ability.share*100:>8.1f}%"
            )
        return "\n".join(lines)


def _press_times(waypoint: Waypoint) -> list[tuple[float, str]]:
    """Momentele apasarilor de tasta dintr-un segment, in secunde de la start."""
    times: list[tuple[float, str]] = []
    elapsed = 0.0
    for event in waypoint.events:
        elapsed += event.dt
        if event.kind == "key_down" and event.key:
            times.append((elapsed, event.key))
    return times


def _cooldown_from_gaps(gaps: list[float], floor: float) -> float:
    """Cea mai scurta reapasare reusita, ignorand cateva valori extreme."""
    if not gaps:
        return floor
    ordered = sorted(gaps)
    if len(ordered) < 4:
        return max(floor, ordered[0])
    index = max(0, int(len(ordered) * 0.15) - 1)
    return max(floor, ordered[index])


def analyze(
    route: Route,
    kinds: Iterable[str] = ("combat",),
    exclude: Optional[Iterable[str]] = None,
    min_presses: int = 3,
) -> Rotation:
    """Extrage rotatia din reperele de tipul cerut.

    `exclude` primeste tastele pe care le stii deja cu alt rost (vindecare,
    loot, selectare tinta): ele apar in lupta, dar nu sunt abilitati de atac.
    """
    excluded = MOVEMENT_KEYS | CHAT_KEYS | {str(k).lower() for k in (exclude or []) if k}
    kinds = set(kinds)

    per_key_times: dict[str, list[float]] = {}
    per_key_gaps: dict[str, list[float]] = {}
    all_times: list[float] = []
    fight_seconds = 0.0
    segments = 0
    offset = 0.0

    for waypoint in route.waypoints:
        if waypoint.kind not in kinds:
            continue
        presses = _press_times(waypoint)
        if not presses:
            continue

        segments += 1
        duration = max(t for t, _ in presses)
        fight_seconds += duration

        for moment, key in presses:
            key = key.lower()
            if key in excluded:
                continue
            # Decalam fiecare segment, ca sa nu iasa intervale negative intre
            # ultima apasare dintr-un segment si prima din urmatorul.
            absolut = offset + moment
            per_key_times.setdefault(key, []).append(absolut)
            all_times.append(absolut)

        offset += duration + 60.0  # separator: segmentele nu sunt continue

    for key, times in per_key_times.items():
        times.sort()
        per_key_gaps[key] = [b - a for a, b in zip(times, times[1:]) if b - a < 300]

    all_times.sort()
    inter = [b - a for a, b in zip(all_times, all_times[1:]) if 0.05 < b - a < 10]
    global_cooldown = round(statistics.median(inter), 2) if inter else 1.5

    total_presses = sum(len(t) for t in per_key_times.values())
    abilities: list[Ability] = []
    for key, times in per_key_times.items():
        if len(times) < min_presses:
            continue  # apasata de doua ori intr-o ora: nu e o abilitate de rotatie
        abilities.append(
            Ability(
                key=key,
                presses=len(times),
                cooldown=_cooldown_from_gaps(per_key_gaps[key], global_cooldown),
                share=len(times) / total_presses if total_presses else 0.0,
            )
        )

    # Ordinea de prioritate: abilitatile cu cooldown mare primele. Ele sunt
    # lovitura grea si vrei sa plece de indata ce e disponibila; cele cu
    # cooldown mic umplu golurile oricum.
    abilities.sort(key=lambda a: (-a.cooldown, -a.presses))

    return Rotation(
        abilities=abilities,
        global_cooldown=global_cooldown,
        fight_seconds=fight_seconds,
        segments=segments,
    )
