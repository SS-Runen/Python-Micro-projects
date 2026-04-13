"""FarmBuildSearch / deeper beam (offline)."""

from __future__ import annotations

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.farm_build_search import FarmBuildSearch
from LoLPerfmon.sim.greedy_farm_build import beam_refined_farm_build, greedy_farm_build


def test_beam_depth_two_increases_leaf_evaluations() -> None:
    data = build_offline_bundle()
    _, _, _, meta1 = beam_refined_farm_build(
        data, "generic_ap", t_max=400.0, beam_depth=1, beam_width=2, max_leaf_evals=30
    )
    _, _, _, meta2 = beam_refined_farm_build(
        data, "generic_ap", t_max=400.0, beam_depth=2, beam_width=2, max_leaf_evals=30
    )
    assert meta2.leaves_evaluated >= meta1.leaves_evaluated


def test_greedy_farm_build_jungle_mode_runs() -> None:
    data = build_offline_bundle()
    order, farm, res, meta = greedy_farm_build(
        data, "generic_ap", t_max=200.0, farm_mode=FarmMode.JUNGLE
    )
    assert res.total_farm_gold == farm
    assert meta.purchase_count == len(order)


def test_farm_build_search_class_api() -> None:
    data = build_offline_bundle()
    search = FarmBuildSearch(
        data=data,
        champion_id="generic_ap",
        farm_mode=FarmMode.LANE,
        t_max=250.0,
        beam_depth=2,
        beam_width=2,
        max_leaf_evals=25,
    )
    order, val, res, meta = search.run()
    assert isinstance(order, tuple)
    assert val == res.total_farm_gold
    assert meta.leaves_evaluated >= 1


def test_farm_build_search_farm_gold_per_gold_spent_leaf_score() -> None:
    data = build_offline_bundle()
    search = FarmBuildSearch(
        data=data,
        champion_id="generic_ap",
        farm_mode=FarmMode.LANE,
        t_max=400.0,
        beam_depth=1,
        beam_width=2,
        max_leaf_evals=15,
        leaf_score="farm_gold_per_gold_spent",
    )
    order, val, res, meta = search.run()
    assert isinstance(order, tuple)
    assert res.total_gold_spent_on_items > 0
    assert abs(val - res.total_farm_gold / res.total_gold_spent_on_items) < 1e-6
    assert meta.leaves_evaluated >= 1


def test_farm_build_search_early_dps_auc_leaf_score() -> None:
    data = build_offline_bundle()
    search = FarmBuildSearch(
        data=data,
        champion_id="generic_ap",
        farm_mode=FarmMode.LANE,
        t_max=300.0,
        beam_depth=1,
        beam_width=2,
        max_leaf_evals=20,
        leaf_score="early_dps_auc",
        early_horizon_seconds=120.0,
    )
    order, val, res, meta = search.run()
    assert isinstance(order, tuple)
    assert val > 0.0
    assert res.total_farm_gold >= 0.0
    assert meta.leaves_evaluated >= 1
