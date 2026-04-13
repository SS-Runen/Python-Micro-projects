"""SimResult throughput aggregate fields (lane/jungle)."""

from __future__ import annotations

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.simulator import PurchasePolicy, simulate


def test_lane_sim_accumulates_total_lane_throughput_units() -> None:
    data = build_offline_bundle(lane_horizon_seconds=300.0)
    res = simulate(
        data,
        "generic_ap",
        FarmMode.LANE,
        PurchasePolicy(buy_order=()),
        t_max=300.0,
    )
    assert res.total_lane_throughput_units >= 0.0
    assert res.total_jungle_route_eff_units == 0.0


def test_jungle_sim_accumulates_route_eff_units() -> None:
    data = build_offline_bundle()
    res = simulate(
        data,
        "generic_ap",
        FarmMode.JUNGLE,
        PurchasePolicy(buy_order=()),
        t_max=120.0,
    )
    assert res.total_jungle_route_eff_units >= 0.0
    assert res.total_lane_throughput_units == 0.0
