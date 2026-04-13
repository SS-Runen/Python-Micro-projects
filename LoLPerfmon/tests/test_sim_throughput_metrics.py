"""SimResult throughput aggregate fields (lane/jungle) and clear-count totals."""

from __future__ import annotations

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.clear import clear_time_seconds, lane_available_seconds, throughput_ratio
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.data_loader import wave_minion_count
from LoLPerfmon.sim.simulator import PurchasePolicy, default_clear_count_score, simulate


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
    assert res.total_jungle_monsters_cleared == res.total_jungle_route_eff_units * data.rules.jungle_monsters_per_route


def test_lane_minions_cleared_matches_first_wave_formula() -> None:
    data = build_offline_bundle(lane_horizon_seconds=120.0)
    t_one_wave = data.rules.first_wave_spawn_seconds
    res = simulate(
        data,
        "generic_ap",
        FarmMode.LANE,
        PurchasePolicy(buy_order=()),
        t_max=t_one_wave,
    )
    w0 = data.wave_at_index(0)
    assert w0 is not None
    rules = data.rules
    t_wave = rules.first_wave_spawn_seconds
    gm = t_wave / 60.0
    from LoLPerfmon.sim.clear import effective_dps
    from LoLPerfmon.sim.stats import total_stats

    profile = data.champions["generic_ap"]
    stats = total_stats(profile, 1, (), data.items)
    dps = effective_dps(profile, 1, stats)
    ct = clear_time_seconds(w0, gm, data, dps)
    lane_win = lane_available_seconds(
        rules.wave_interval_seconds,
        rules.lane_engagement_overhead_seconds,
    )
    thr = throughput_ratio(ct, lane_win)
    expected_first = thr * float(wave_minion_count(w0))
    assert abs(res.total_lane_minions_cleared - expected_first) < 1e-6


def test_lane_engagement_overhead_reduces_throughput_vs_full_interval() -> None:
    ct = 40.0
    wi = 30.0
    thr_full = throughput_ratio(ct, wi)
    win = lane_available_seconds(wi, 10.0)
    thr_eng = throughput_ratio(ct, win)
    assert thr_eng < thr_full


def test_default_clear_count_score_dispatches_by_mode() -> None:
    data = build_offline_bundle(lane_horizon_seconds=120.0)
    r_lane = simulate(data, "generic_ap", FarmMode.LANE, PurchasePolicy(buy_order=()), t_max=120.0)
    r_j = simulate(data, "generic_ap", FarmMode.JUNGLE, PurchasePolicy(buy_order=()), t_max=60.0)
    assert default_clear_count_score(r_lane, FarmMode.LANE) == r_lane.total_lane_minions_cleared
    assert default_clear_count_score(r_j, FarmMode.JUNGLE) == r_j.total_jungle_monsters_cleared
