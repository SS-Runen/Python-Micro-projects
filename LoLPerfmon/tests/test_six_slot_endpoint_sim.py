"""Six terminal slots, unbounded time, and lane wave extrapolation."""

from __future__ import annotations

from dataclasses import replace

import pytest

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.data_loader import GameDataBundle
from LoLPerfmon.sim.greedy_farm_build import make_early_stop_six_build_endpoints
from LoLPerfmon.sim.models import ItemDef, StatBonus, is_build_endpoint_item
from LoLPerfmon.sim.simulator import PurchasePolicy, SimulationState, simulate
from LoLPerfmon.sim.wave_schedule import generate_lane_waves_until, wave_composition_at_index


def test_is_build_endpoint_item() -> None:
    terminal = ItemDef("t", "T", 100.0, StatBonus(), (), into_ids=())
    comp = ItemDef("c", "C", 50.0, StatBonus(), (), into_ids=("t",))
    assert is_build_endpoint_item(terminal) is True
    assert is_build_endpoint_item(comp) is False


def test_wave_composition_matches_generated_list() -> None:
    waves = generate_lane_waves_until(500.0, 35.0, 30.0)
    for w in waves:
        assert wave_composition_at_index(w.wave_index) == w


def test_simulate_inf_without_early_stop_raises() -> None:
    data = build_offline_bundle()
    with pytest.raises(ValueError, match="inf requires early_stop"):
        simulate(
            data,
            "generic_ap",
            FarmMode.LANE,
            PurchasePolicy(buy_order=()),
            t_max=float("inf"),
        )


def test_extrapolate_lane_waves_more_income_than_truncated_list() -> None:
    data = build_offline_bundle(lane_horizon_seconds=200.0)
    assert len(data.waves) < 50
    base = simulate(
        data,
        "generic_ap",
        FarmMode.LANE,
        PurchasePolicy(buy_order=()),
        t_max=50_000.0,
        extrapolate_lane_waves=False,
    )
    extended = simulate(
        data,
        "generic_ap",
        FarmMode.LANE,
        PurchasePolicy(buy_order=()),
        t_max=50_000.0,
        extrapolate_lane_waves=True,
    )
    assert extended.total_farm_gold > base.total_farm_gold


def test_early_stop_six_endpoints_state_only() -> None:
    t1 = ItemDef("t1", "T1", 10.0, StatBonus(), (), into_ids=())
    t2 = ItemDef("t2", "T2", 10.0, StatBonus(), (), into_ids=())
    c = ItemDef("c1", "C1", 10.0, StatBonus(), (), into_ids=("t1",))
    items = {t1.id: t1, t2.id: t2, c.id: c}
    stop = make_early_stop_six_build_endpoints(items)

    def st(inv: list[str]) -> SimulationState:
        return SimulationState(
            time_seconds=100.0,
            gold=0.0,
            inventory=list(inv),
            total_xp=0.0,
            level=1,
            buy_queue=[],
            total_gold_spent_on_items=0.0,
        )

    six_term = ["t1", "t2", "t1", "t2", "t1", "t2"]
    assert stop(st(six_term)) is True
    assert stop(st(six_term[:5])) is False
    bad = ["t1", "t2", "t1", "t2", "t1", "c1"]
    assert stop(st(bad)) is False


def test_six_slot_sim_ends_with_inf_and_early_stop() -> None:
    ob = build_offline_bundle(lane_horizon_seconds=500.0)

    leaves: dict[str, ItemDef] = {}
    for i in range(6):
        lid = f"leaf_ep_{i}"
        leaves[lid] = ItemDef(
            lid,
            f"Leaf EP {i}",
            1.0,
            StatBonus(ability_power=float(i + 1)),
            (),
            into_ids=(),
            max_inventory_copies=1,
        )
    items = dict(ob.items)
    items.update(leaves)
    data = GameDataBundle(
        rules=replace(ob.rules, start_gold=1_000_000.0),
        champions=ob.champions,
        items=items,
        waves=ob.waves,
        minion_economy=ob.minion_economy,
        data_dir=None,
    )
    order = tuple(leaves.keys())
    early = make_early_stop_six_build_endpoints(data.items)
    res = simulate(
        data,
        "generic_ap",
        FarmMode.LANE,
        PurchasePolicy(buy_order=order),
        t_max=float("inf"),
        early_stop=early,
        extrapolate_lane_waves=True,
    )
    assert res.ended_by_early_stop is True
    assert len(res.final_inventory) == 6
    assert all(is_build_endpoint_item(data.items[i]) for i in res.final_inventory)


def test_best_item_order_exhaustive_threads_inf_and_extrapolate() -> None:
    from LoLPerfmon.sim.optimizer import best_item_order_exhaustive

    data = build_offline_bundle(lane_horizon_seconds=800.0)
    _order, _score, res = best_item_order_exhaustive(
        data,
        "generic_ap",
        FarmMode.LANE,
        ("cheap_ap",),
        t_max=float("inf"),
        early_stop=lambda s: s.time_seconds >= 150.0,
        extrapolate_lane_waves=True,
    )
    assert res.ended_by_early_stop is True
    assert res.timeline[-1][0] >= 149.0

