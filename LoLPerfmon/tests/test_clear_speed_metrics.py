"""Tests for τ (time to saturated throughput) and farm ROI helpers."""

from __future__ import annotations

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.clear import clear_time_seconds, lane_available_seconds, throughput_ratio
from LoLPerfmon.sim.clear_speed_metrics import (
    farm_income_per_gold_spent,
    time_to_saturated_farm_throughput,
)
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.greedy_farm_build import make_greedy_hook
from LoLPerfmon.sim.simulator import PurchasePolicy, SimResult, simulate


def test_farm_income_per_gold_spent_ratio() -> None:
    res = SimResult(
        final_gold=0.0,
        final_level=1.0,
        final_inventory=(),
        timeline=[],
        total_farm_gold=1000.0,
        total_passive_gold=0.0,
        total_gold_spent_on_items=500.0,
        starting_gold=500.0,
        net_wealth_delta=0.0,
    )
    assert abs(farm_income_per_gold_spent(res) - 2.0) < 1e-9


def test_time_to_saturated_lane_smoke_offline() -> None:
    data = build_offline_bundle(lane_horizon_seconds=3600.0)
    profile = data.champions["generic_ap"]
    hook = make_greedy_hook(
        profile,
        data.items,
        None,
        1e-9,
        order_sink=None,
        data=data,
        farm_mode=FarmMode.LANE,
        eta_lane=1.0,
        marginal_income_cap=True,
    )
    tau, res = time_to_saturated_farm_throughput(
        data,
        "generic_ap",
        FarmMode.LANE,
        hook,
        t_max=600.0,
    )
    assert res.total_farm_gold >= 0.0
    assert tau is None or (isinstance(tau, float) and tau >= 0.0)


def test_tau_matches_inline_lane_callback_offline() -> None:
    """First wave time where throughput hits cap should match ``time_to_saturated``."""
    data = build_offline_bundle(lane_horizon_seconds=3600.0)
    profile = data.champions["generic_ap"]
    hook = make_greedy_hook(
        profile,
        data.items,
        None,
        1e-9,
        order_sink=None,
        data=data,
        farm_mode=FarmMode.LANE,
        eta_lane=1.0,
        marginal_income_cap=True,
    )
    tau_module, _ = time_to_saturated_farm_throughput(
        data,
        "generic_ap",
        FarmMode.LANE,
        hook,
        t_max=1200.0,
    )

    first_inline: float | None = None
    rules = data.rules

    def lane_cb(t_wave: float, k: int, dps: float) -> None:
        nonlocal first_inline
        if first_inline is not None:
            return
        wave = data.wave_at_index(k)
        if wave is None:
            return
        gm = t_wave / 60.0
        ct = clear_time_seconds(wave, gm, data, dps)
        lane_win = lane_available_seconds(
            rules.wave_interval_seconds,
            rules.lane_engagement_overhead_seconds,
        )
        thr = throughput_ratio(ct, lane_win)
        if thr + 1e-9 >= 1.0:
            first_inline = t_wave

    simulate(
        data,
        "generic_ap",
        FarmMode.LANE,
        PurchasePolicy(buy_order=()),
        eta_lane=1.0,
        t_max=1200.0,
        purchase_hook=hook,
        on_lane_clear_dps=lane_cb,
    )
    assert tau_module == first_inline
