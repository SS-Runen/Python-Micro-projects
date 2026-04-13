"""Jungle companion init, sell, optimal sell timing (offline bundle)."""

from __future__ import annotations

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.jungle_items import (
    JUNGLE_COMPANION_SELL_REFUND_FRACTION,
    jungle_companion_item_ids_sorted,
    jungle_pet_companion_item_ids_sorted,
)
from LoLPerfmon.sim.jungle_sell_timing import optimal_jungle_sell_timing
from LoLPerfmon.sim.simulator import PurchasePolicy, simulate


def test_jungle_starts_with_companion_in_inventory() -> None:
    data = build_offline_bundle()
    cid = "generic_ap"
    res = simulate(
        data,
        cid,
        FarmMode.JUNGLE,
        PurchasePolicy(buy_order=()),
        t_max=200.0,
        jungle_starter_item_id="offline_jungle_pet",
    )
    assert "offline_jungle_pet" in res.final_inventory


def test_jungle_sell_refund_50_percent() -> None:
    data = build_offline_bundle()
    cid = "generic_ap"
    pet = "offline_jungle_pet"
    cost = data.items[pet].total_cost
    res = simulate(
        data,
        cid,
        FarmMode.JUNGLE,
        PurchasePolicy(buy_order=()),
        t_max=500.0,
        jungle_starter_item_id=pet,
        jungle_sell_at_seconds=90.0,
        jungle_sell_only_after_level_18=False,
    )
    assert pet not in res.final_inventory
    # Sold once: wallet includes 50% of sticker; farm also accrued
    assert res.final_gold > data.rules.start_gold - cost + cost * JUNGLE_COMPANION_SELL_REFUND_FRACTION * 0.99


def test_offline_bundle_lists_one_jungle_companion() -> None:
    data = build_offline_bundle()
    assert jungle_companion_item_ids_sorted(data) == ["offline_jungle_pet"]
    assert jungle_pet_companion_item_ids_sorted(data) == ["offline_jungle_pet"]


def test_optimal_jungle_sell_timing_runs() -> None:
    data = build_offline_bundle()
    best_t, score, res = optimal_jungle_sell_timing(
        data, "generic_ap", t_max=800.0, jungle_starter_item_id="offline_jungle_pet"
    )
    assert res.total_farm_gold == score
    assert best_t is None or best_t >= data.rules.jungle_base_cycle_seconds
