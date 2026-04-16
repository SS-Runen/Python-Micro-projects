from __future__ import annotations

from enum import Enum


class FarmMode(str, Enum):
    LANE = "lane"
    JUNGLE = "jungle"


STARTING_GOLD = 500.0
PASSIVE_GOLD_PER_SEC = 1.6
PASSIVE_GOLD_AT_5MIN = 480.0
LANE_MINIONS_FIRST_SPAWN_SEC = 30.0
JUNGLE_CAMPS_FIRST_SPAWN_SEC = 60.0
MAX_INVENTORY_SLOTS = 6

HORIZONS_SEC = (15 * 60, 25 * 60, 40 * 60)
