"""General shop sell (50% of total_cost)."""

from __future__ import annotations

from LoLPerfmon.sim.models import ItemDef, StatBonus
from LoLPerfmon.sim.sell_economy import STANDARD_SHOP_SELL_REFUND_FRACTION, shop_sell_refund_gold
from LoLPerfmon.sim.simulator import SimulationState, sell_item_once


def test_shop_sell_refund_half_sticker() -> None:
    it = ItemDef("x", "X", 1000.0, StatBonus(), ())
    assert abs(shop_sell_refund_gold(it) - 500.0) < 1e-9
    assert STANDARD_SHOP_SELL_REFUND_FRACTION == 0.5


def test_sell_item_once_credits_gold_and_frees_block() -> None:
    it = ItemDef("a", "A", 200.0, StatBonus(ability_power=10.0), (), max_inventory_copies=1)
    items = {it.id: it}
    st = SimulationState(
        time_seconds=0.0,
        gold=0.0,
        inventory=["a"],
        total_xp=0.0,
        level=1,
        buy_queue=[],
        total_gold_spent_on_items=200.0,
        blocked_purchase_ids={"a"},
    )
    assert sell_item_once(st, "a", items)
    assert st.inventory == []
    assert abs(st.gold - 100.0) < 1e-9
    assert "a" not in st.blocked_purchase_ids
