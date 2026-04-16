from __future__ import annotations

from collections import Counter

from LoLPerfmon.sim.config import MAX_INVENTORY_SLOTS
from LoLPerfmon.sim.models import ItemStatic


def combine_gold_cost(target: ItemStatic, items: dict[str, ItemStatic]) -> float:
    """Gold to pay when upgrading from recipe components already owned.

    If ``builds_from`` is empty, returns full ``target.cost`` (full shop purchase).
    """
    if not target.builds_from:
        return float(target.cost)
    parts = sum(float(items[cid].cost) for cid in target.builds_from if cid in items)
    return max(0.0, float(target.cost) - parts)


def inventory_counts(inventory: list[str | None]) -> Counter[str]:
    c: Counter[str] = Counter()
    for slot in inventory:
        if slot:
            c[slot] += 1
    return c


def can_combine_recipe(
    inventory: list[str | None],
    items: dict[str, ItemStatic],
    target_item_id: str,
) -> bool:
    if target_item_id not in items:
        return False
    target = items[target_item_id]
    if not target.builds_from:
        return False
    need = Counter(target.builds_from)
    have = inventory_counts(inventory)
    return all(have[k] >= need[k] for k in need)


def complete_recipe_in_inventory(
    inventory: list[str | None],
    items: dict[str, ItemStatic],
    target_item_id: str,
) -> list[str | None]:
    """Return a new 6-slot inventory: remove recipe components, add ``target_item_id`` in lowest free slot."""
    if len(inventory) != MAX_INVENTORY_SLOTS:
        raise ValueError(f"inventory must have {MAX_INVENTORY_SLOTS} slots")
    if target_item_id not in items:
        raise KeyError(target_item_id)
    target = items[target_item_id]
    if not target.builds_from:
        raise ValueError("target has no recipe")
    need = Counter(target.builds_from)
    have = inventory_counts(inventory)
    if not all(have[k] >= need[k] for k in need):
        raise ValueError("missing recipe components in inventory")

    out = list(inventory)
    for i in range(len(out)):
        if out[i] and need[out[i]] > 0:
            need[out[i]] -= 1
            out[i] = None
    if any(need.values()):
        raise ValueError("could not remove recipe components")

    for i in range(len(out)):
        if out[i] is None:
            out[i] = target_item_id
            return out
    raise ValueError("no free slot for completed item")
