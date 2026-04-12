"""
Post-simulation marginal clear / DPS checks (no selling or item replacement).

Used to report whether another full purchase could still increase ``effective_dps``
given final level, inventory, and gold.
"""

from __future__ import annotations

from .clear import effective_dps
from .data_loader import GameDataBundle
from .simulator import MAX_INVENTORY_SLOTS, SimResult
from .stats import total_stats


def clear_upgrade_report(
    data: GameDataBundle,
    champion_id: str,
    res: SimResult,
) -> tuple[bool, list[tuple[str, float, float]]]:
    """
    After a run, consider **adding one** finished item by paying ``ItemDef.total_cost`` if
    ``final_gold`` suffices and a slot exists (``len(inventory) < MAX_INVENTORY_SLOTS``).

    Returns ``(saturated, rows)`` where ``rows`` are ``(item_id, delta_effective_dps, cost)``
    for affordable items with **positive** ``delta_effective_dps``, sorted by delta descending.

    ``saturated`` is True when no such row exists (no modeled one-step DPS gain from a full buy).

    Does not evaluate crafts from partial components, swaps, or selling. If the bag is full,
    returns ``(True, [])`` (no hypothetical add modeled).
    """
    if champion_id not in data.champions:
        raise KeyError(champion_id)
    profile = data.champions[champion_id]
    inv = list(res.final_inventory)
    lvl = int(res.final_level)
    gold = res.final_gold
    items = data.items

    if len(inv) >= MAX_INVENTORY_SLOTS:
        return True, []

    base_stats = total_stats(profile, lvl, tuple(inv), items)
    base_dps = effective_dps(profile, lvl, base_stats)

    rows: list[tuple[str, float, float]] = []
    for iid, idef in items.items():
        if gold + 1e-9 < idef.total_cost:
            continue
        st = total_stats(profile, lvl, tuple(inv + [iid]), items)
        delta = effective_dps(profile, lvl, st) - base_dps
        if delta > 1e-12:
            rows.append((iid, delta, idef.total_cost))

    rows.sort(key=lambda t: -t[1])
    return (len(rows) == 0, rows)
