"""
End-to-end: full SR horizon (60:00), lane + jungle, offline bundle.

This is the closest automated equivalent to a full match-length simulation without a game client.
"""

from __future__ import annotations

import os

import pytest

from LoLPerfmon.sim.bundle_factory import get_game_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.simulator import PurchasePolicy, simulate
from LoLPerfmon.sim.test_champion_ids import primary_champion_id, two_cheapest_item_ids


def test_e2e_lane_full_horizon_offline() -> None:
    data = get_game_bundle(offline=True)
    cid = primary_champion_id(data)
    res = simulate(
        data,
        cid,
        FarmMode.LANE,
        PurchasePolicy(buy_order=()),
        t_max=3600.0,
    )
    assert res.final_level <= 18.0
    assert res.final_level >= 1.0
    assert res.final_gold > data.rules.start_gold
    assert res.total_farm_gold > 0
    assert res.total_passive_gold > 0
    assert len(res.timeline) >= 2


def test_e2e_jungle_full_horizon_offline() -> None:
    data = get_game_bundle(offline=True)
    cid = primary_champion_id(data)
    res = simulate(
        data,
        cid,
        FarmMode.JUNGLE,
        PurchasePolicy(buy_order=()),
        t_max=3600.0,
    )
    assert res.final_gold > data.rules.start_gold
    assert res.total_farm_gold > 0


def test_e2e_buy_two_cheapest_full_horizon_offline() -> None:
    data = get_game_bundle(offline=True)
    cid = primary_champion_id(data)
    a, b = two_cheapest_item_ids(data)
    res = simulate(
        data,
        cid,
        FarmMode.LANE,
        PurchasePolicy(buy_order=(a, b)),
        t_max=3600.0,
    )
    assert len(res.final_inventory) == 2
    assert a in res.final_inventory and b in res.final_inventory


@pytest.mark.integration
def test_e2e_lane_data_dragon_bundle_if_online() -> None:
    if os.environ.get("LOLPERFMON_OFFLINE", "1").lower() in ("1", "true", "yes"):
        pytest.skip("Set LOLPERFMON_OFFLINE=0 to attempt Data Dragon fetch")
    data = get_game_bundle(offline=False)
    if data.rules.patch_version == "offline-computed":
        pytest.skip("Data Dragon unavailable in this environment")
    cid = primary_champion_id(data)
    res = simulate(data, cid, FarmMode.LANE, PurchasePolicy(buy_order=()), t_max=120.0)
    assert res.final_gold > 0
