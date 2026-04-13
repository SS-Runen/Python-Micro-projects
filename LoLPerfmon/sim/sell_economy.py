"""
Unified shop sell refund (deterministic model).

Selling an item credits a fixed fraction of the item sticker ``total_cost`` (assumption A9 in
the farm policy plan). Live League uses Data Dragon ``gold.sell`` per item; this codebase
uses one fraction for clarity and reproducibility unless extended later.
"""

from __future__ import annotations

from .models import ItemDef

# Plan assumption A9: 50% of purchase value (`total_cost`) returned on sell.
STANDARD_SHOP_SELL_REFUND_FRACTION = 0.5


def shop_sell_refund_gold(it: ItemDef) -> float:
    return float(it.total_cost) * STANDARD_SHOP_SELL_REFUND_FRACTION


__all__ = [
    "STANDARD_SHOP_SELL_REFUND_FRACTION",
    "shop_sell_refund_gold",
]
