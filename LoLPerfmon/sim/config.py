from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FarmMode(str, Enum):
    LANE = "lane"
    JUNGLE = "jungle"


@dataclass(frozen=True)
class GameConfig:
    map_name: str = "SummonersRift"
    mode_5v5_classic: bool = True
    start_gold: float = 500.0
    passive_gold_per_10_seconds: float = 20.4
    passive_gold_start_seconds: float = 65.0
    t_max_seconds: float = 3600.0
    patch_version: str = "synthetic_15.0"

    def passive_rate_per_second(self) -> float:
        return self.passive_gold_per_10_seconds / 10.0
