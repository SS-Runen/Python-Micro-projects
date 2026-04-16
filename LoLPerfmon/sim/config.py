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

# CLI / runner: default farm targets (``UnitStatic`` ids under data/minions, data/monsters)
DEFAULT_LANE_UNIT_ID = "lane_melee"
DEFAULT_JUNGLE_UNIT_ID = "raptor_small"

# Optional 00:00 starting purchase (item_id keys in bundled JSON); jungler uses a generic component
# when no jungle-specific item exists in the catalog.
DEFAULT_LANER_STARTER_ITEM_ID = "amplifying_tome"
DEFAULT_JUNGLER_STARTER_ITEM_ID = "dagger"
