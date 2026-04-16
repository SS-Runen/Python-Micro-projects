from __future__ import annotations

from LoLPerfmon.sim.config import (
    DEFAULT_JUNGLER_STARTER_ITEM_ID,
    DEFAULT_LANER_STARTER_ITEM_ID,
    DEFAULT_JUNGLE_UNIT_ID,
    DEFAULT_LANE_UNIT_ID,
    FarmMode,
)
from LoLPerfmon.sim.models import ItemStatic, UnitStatic


def farm_mode_from_role(role: str) -> FarmMode:
    r = role.strip().lower()
    if r == "laner":
        return FarmMode.LANE
    if r == "jungler":
        return FarmMode.JUNGLE
    raise ValueError(f"unknown role {role!r}; expected 'laner' or 'jungler'")


def resolve_item_id(name_or_id: str, items_catalog: dict[str, ItemStatic]) -> str:
    raw = name_or_id.strip()
    if not raw:
        raise ValueError("empty item name or id")
    key = raw.lower().replace(" ", "_")
    if key in items_catalog:
        return key
    low = raw.lower()
    for iid, it in items_catalog.items():
        if it.name.lower() == low:
            return iid
    raise ValueError(f"unknown item {name_or_id!r}")


def resolve_starter_item_id(
    mode: FarmMode,
    explicit: str | None,
    *,
    no_starter: bool,
    items_catalog: dict[str, ItemStatic],
) -> str | None:
    if no_starter:
        return None
    if explicit:
        return resolve_item_id(explicit, items_catalog)
    default = DEFAULT_LANER_STARTER_ITEM_ID if mode == FarmMode.LANE else DEFAULT_JUNGLER_STARTER_ITEM_ID
    if default in items_catalog:
        return default
    return None


def default_lane_minion(units: dict[str, UnitStatic]) -> UnitStatic | None:
    return units.get(DEFAULT_LANE_UNIT_ID)


def default_jungle_monster(units: dict[str, UnitStatic]) -> UnitStatic | None:
    return units.get(DEFAULT_JUNGLE_UNIT_ID)
