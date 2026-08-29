"""Incarcarea profilului de joc.

Fiecare joc are alta interfata, deci tot ce e specific (unde e bara de viata,
ce culoare au nameplate-urile, ce tasta e atacul) sta intr-un YAML separat, in
`profiles/`. Codul nu contine nimic legat de un joc anume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .capture import Region

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


@dataclass
class ColorRange:
    """Interval HSV. In OpenCV: H 0-179, S 0-255, V 0-255."""

    low: tuple[int, int, int]
    high: tuple[int, int, int]

    @classmethod
    def from_dict(cls, data: dict) -> "ColorRange":
        return cls(tuple(data["low"]), tuple(data["high"]))  # type: ignore[arg-type]


@dataclass
class Profile:
    """Tot ce stie botul despre jocul tau."""

    name: str = "implicit"
    monitor: int = 1
    raw: dict[str, Any] = field(default_factory=dict)

    regions: dict[str, Region] = field(default_factory=dict)
    colors: dict[str, ColorRange] = field(default_factory=dict)
    keys: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    behaviors: dict[str, bool] = field(default_factory=dict)
    safety: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------- incarcare

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        if yaml is None:
            raise RuntimeError("PyYAML nu e instalat. pip install -r gamebot/requirements.txt")
        file = Path(path)
        if not file.exists():
            raise FileNotFoundError(
                f"Nu gasesc profilul {file}. Porneste de la gamebot/profiles/exemplu.yaml"
            )
        data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        profile = cls(
            name=data.get("name", "implicit"),
            monitor=int(data.get("monitor", 1)),
            raw=data,
        )
        profile.regions = {
            key: Region.from_dict(value)
            for key, value in (data.get("regions") or {}).items()
        }
        profile.colors = {
            key: ColorRange.from_dict(value)
            for key, value in (data.get("colors") or {}).items()
        }
        profile.keys = data.get("keys") or {}
        profile.thresholds = data.get("thresholds") or {}
        profile.behaviors = data.get("behaviors") or {}
        profile.safety = data.get("safety") or {}
        return profile

    # --------------------------------------------------------------- acces

    def region(self, name: str) -> Optional[Region]:
        return self.regions.get(name)

    def color(self, name: str) -> Optional[ColorRange]:
        return self.colors.get(name)

    def key(self, name: str, default: Any = None) -> Any:
        return self.keys.get(name, default)

    def threshold(self, name: str, default: float) -> float:
        return float(self.thresholds.get(name, default))

    def enabled(self, behavior: str, default: bool = False) -> bool:
        return bool(self.behaviors.get(behavior, default))

    def section(self, name: str) -> dict:
        """Sectiune libera din YAML (de ex. `combat:` sau `ui_loop:`)."""
        return self.raw.get(name) or {}

    def missing_pieces(self) -> list[str]:
        """Ce lipseste din profil ca botul sa functioneze corect.

        Rulat la pornire: mai bine afli acum ca n-ai definit bara de viata,
        decat dupa ce personajul moare de trei ori.
        """
        problems: list[str] = []
        if self.enabled("survival") and "health_bar" not in self.regions:
            problems.append("regions.health_bar lipseste, dar comportamentul 'survival' e activ")
        if self.enabled("survival") and "health" not in self.colors:
            problems.append("colors.health lipseste (culoarea barei de viata)")
        if self.enabled("combat") and not self.key("attack_rotation"):
            problems.append("keys.attack_rotation lipseste (tastele de atac)")
        if self.enabled("gather") and "resource_node" not in self.colors:
            problems.append("colors.resource_node lipseste (culoarea nodurilor)")
        if "minimap" not in self.regions:
            problems.append("regions.minimap lipseste - localizarea pe ruta va fi dezactivata")
        return problems
