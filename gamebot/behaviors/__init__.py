"""Comportamentele botului, in ordinea prioritatii lor implicite."""

from .survival import SurvivalBehavior
from .combat import CombatBehavior
from .loot import LootBehavior
from .gather import GatherBehavior
from .upkeep import UpkeepBehavior
from .mount import MountBehavior
from .idle_click import IdleClickBehavior
from .travel import TravelBehavior

ALL_BEHAVIORS = [
    SurvivalBehavior,
    CombatBehavior,
    LootBehavior,
    GatherBehavior,
    UpkeepBehavior,
    MountBehavior,
    IdleClickBehavior,
    TravelBehavior,
]

__all__ = [cls.__name__ for cls in ALL_BEHAVIORS] + ["ALL_BEHAVIORS"]
