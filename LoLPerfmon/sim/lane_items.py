"""
Lane starter items (Doran's line, Dark Seal, …) and sell pricing.

Data Dragon marks many starters as **build endpoints** (empty ``into``) because they have no
shop upgrades in the item graph; the simulator can still **sell** them for gold like the
client (see :func:`~LoLPerfmon.sim.simulator.sell_lane_starter_once`).
"""

from __future__ import annotations

from .models import ItemDef

# When Data Dragon omits ``gold.sell``, many starters use ~40% of sticker price.
LANE_STARTER_SELL_REFUND_FALLBACK = 0.4


def is_resellable_lane_starter(it: ItemDef) -> bool:
    """
    Starters that can be sold for gold in this model: no recipe ``from``, not a consumable,
    and either Doran's-style (``Lane`` tag, no ``into``) or **Dark Seal** (id 1082), which
    upgrades in the graph but is still sold like a starter.
    """
    if "Consumable" in it.tags:
        return False
    if it.from_ids:
        return False
    if it.id == "1082":
        return True
    return "Lane" in it.tags and len(it.into_ids) == 0


def lane_starter_sell_value(it: ItemDef) -> float:
    if it.sell_gold is not None:
        return float(it.sell_gold)
    return LANE_STARTER_SELL_REFUND_FALLBACK * float(it.total_cost)


__all__ = [
    "LANE_STARTER_SELL_REFUND_FALLBACK",
    "is_resellable_lane_starter",
    "lane_starter_sell_value",
]
