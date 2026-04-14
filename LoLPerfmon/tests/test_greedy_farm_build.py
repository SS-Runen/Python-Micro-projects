"""Offline smoke: stepwise path-aware / beam farm build (no Data Dragon)."""

from __future__ import annotations

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.greedy_farm_build import (
    BeamFarmMetadata,
    StepwiseFarmMetadata,
    beam_refined_farm_build,
    ranked_marginal_acquisitions,
    stepwise_farm_build,
)
from LoLPerfmon.sim.simulator import SimulationState


def test_stepwise_farm_build_smoke_offline() -> None:
    data = build_offline_bundle()
    order, farm, res, meta = stepwise_farm_build(data, "generic_ap", t_max=300.0)
    assert res.total_farm_gold == farm
    assert isinstance(order, tuple)
    if isinstance(meta, StepwiseFarmMetadata):
        assert meta.purchase_count == len(order)
    else:
        assert isinstance(meta, BeamFarmMetadata)


def test_ranked_marginals_deterministic_order() -> None:
    data = build_offline_bundle()
    profile = data.champions["generic_ap"]
    st = SimulationState(
        time_seconds=0.0,
        gold=float(data.rules.start_gold),
        inventory=[],
        total_xp=0.0,
        level=1,
        buy_queue=[],
        total_gold_spent_on_items=0.0,
    )
    r1 = ranked_marginal_acquisitions(st, profile, data.items, 1e-9)
    r2 = ranked_marginal_acquisitions(st, profile, data.items, 1e-9)
    assert r1 == r2


def test_stepwise_matches_minimal_beam_config() -> None:
    data = build_offline_bundle()
    _, s_farm, _, _ = stepwise_farm_build(data, "generic_ap", t_max=120.0, meaningful_exploration=False)
    _, b_farm, _, meta_b = beam_refined_farm_build(
        data,
        "generic_ap",
        t_max=120.0,
        beam_depth=1,
        beam_width=1,
        max_leaf_evals=8,
        marginal_objective="horizon_greedy_roi",
        meaningful_exploration=False,
    )
    assert isinstance(meta_b, BeamFarmMetadata)
    assert abs(s_farm - b_farm) < 1e-6
