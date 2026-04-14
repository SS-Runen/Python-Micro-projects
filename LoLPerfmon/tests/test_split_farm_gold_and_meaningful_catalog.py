"""Split lane vs jungle farm gold on SimResult; meaningful exploration catalog smoke tests."""

from __future__ import annotations

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.item_heuristics import (
    meaningful_waveclear_exploration_catalog,
    waveclear_relevant_item_catalog,
)
from LoLPerfmon.sim.models import ItemDef, StatBonus
from LoLPerfmon.sim.simulator import PurchasePolicy, gold_flow_reconciliation_error, primary_farm_gold_for_mode, simulate


def test_lane_run_populates_only_lane_minion_farm_gold() -> None:
    data = build_offline_bundle(lane_horizon_seconds=600.0)
    res = simulate(
        data,
        "generic_ap",
        FarmMode.LANE,
        PurchasePolicy(buy_order=()),
        eta_lane=1.0,
        t_max=300.0,
    )
    assert res.total_jungle_monster_farm_gold == 0.0
    assert res.total_lane_minion_farm_gold > 0.0
    assert abs(res.total_farm_gold - res.total_lane_minion_farm_gold) < 1e-6
    assert abs(primary_farm_gold_for_mode(res, FarmMode.LANE) - res.total_farm_gold) < 1e-6
    assert gold_flow_reconciliation_error(res) < 1e-5


def test_jungle_run_populates_only_jungle_monster_farm_gold() -> None:
    data = build_offline_bundle(lane_horizon_seconds=600.0)
    res = simulate(
        data,
        "generic_ap",
        FarmMode.JUNGLE,
        PurchasePolicy(buy_order=()),
        eta_lane=1.0,
        t_max=120.0,
    )
    assert res.total_lane_minion_farm_gold == 0.0
    assert res.total_jungle_monster_farm_gold > 0.0
    assert abs(res.total_farm_gold - res.total_jungle_monster_farm_gold) < 1e-6
    assert abs(primary_farm_gold_for_mode(res, FarmMode.JUNGLE) - res.total_farm_gold) < 1e-6
    assert gold_flow_reconciliation_error(res) < 1e-5


def test_meaningful_catalog_nonempty_and_recipe_closed_offline() -> None:
    data = build_offline_bundle(lane_horizon_seconds=600.0)
    profile = data.champions["generic_ap"]
    full = meaningful_waveclear_exploration_catalog(data.items, FarmMode.LANE, profile)
    assert len(full) >= 1
    for iid, it in full.items():
        assert iid in data.items
        for fid in it.from_ids:
            assert fid in full


def test_waveclear_relevant_catalog_no_full_fallback_when_no_relevant_stats() -> None:
    data = build_offline_bundle(lane_horizon_seconds=600.0)
    profile = data.champions["generic_ap"]
    inert_items = {
        "hp_only": ItemDef(
            id="hp_only",
            name="HP only",
            total_cost=500.0,
            stats=StatBonus(health=200.0),
            from_ids=(),
            into_ids=(),
        )
    }
    strict = waveclear_relevant_item_catalog(
        inert_items,
        FarmMode.LANE,
        profile,
        allow_full_catalog_fallback=False,
    )
    assert strict == {}
    legacy = waveclear_relevant_item_catalog(
        inert_items,
        FarmMode.LANE,
        profile,
        allow_full_catalog_fallback=True,
    )
    assert "hp_only" in legacy
