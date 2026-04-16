"""Wider checks for passive income vs farm gold in ``simulate_farm_horizon`` / ``simulate_with_buy_order``."""

from __future__ import annotations

import pytest

from LoLPerfmon.data.loaders import data_root_default, load_bundle
from LoLPerfmon.sim.config import (
    FarmMode,
    PASSIVE_GOLD_AT_5MIN,
    PASSIVE_GOLD_PER_SEC,
    STARTING_GOLD,
)
from LoLPerfmon.sim.economy import passive_gold_over_interval, starting_wallet
from LoLPerfmon.sim.simulator import simulate_farm_horizon, simulate_with_buy_order


def test_config_starting_gold_and_passive_rate_match_design() -> None:
    assert STARTING_GOLD == 500.0
    assert PASSIVE_GOLD_PER_SEC == 1.6
    assert abs(PASSIVE_GOLD_AT_5MIN - 300.0 * PASSIVE_GOLD_PER_SEC) < 1e-9


def test_starting_wallet_helper() -> None:
    assert starting_wallet() == STARTING_GOLD


def test_passive_gold_over_five_minutes_is_480() -> None:
    """300 s × 1.6 gold/s = 480 passive gold (no farming)."""
    assert passive_gold_over_interval(300.0) == pytest.approx(480.0, rel=0.0, abs=1e-9)


def test_zero_duration_simulation_preserves_starting_gold() -> None:
    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    res = simulate_farm_horizon(
        ch["lux"],
        FarmMode.LANE,
        items,
        [None] * 6,
        0.0,
        lane_minion=units["lane_melee"],
    )
    assert res.final_wallet == pytest.approx(STARTING_GOLD)
    assert res.passive_gold_total == 0.0
    assert res.total_farm_gold == 0.0


def test_three_minute_lane_passive_and_farming() -> None:
    """Through 3:00: passive accrues at 1.6/s; farm gold is separate and positive."""
    t_three_min = 3.0 * 60.0
    expected_passive = PASSIVE_GOLD_PER_SEC * t_three_min

    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    res = simulate_farm_horizon(
        ch["lux"],
        FarmMode.LANE,
        items,
        [None] * 6,
        t_three_min,
        lane_minion=units["lane_melee"],
        dt=1.0,
    )
    assert res.passive_gold_total == pytest.approx(expected_passive, rel=0.0, abs=0.02)
    assert res.total_farm_gold > 0.0
    assert res.gold_spent == 0.0
    assert res.final_wallet == pytest.approx(
        STARTING_GOLD + res.passive_gold_total + res.total_farm_gold,
        rel=0.0,
        abs=0.02,
    )


def test_five_minute_passive_income_480_excludes_farm_component() -> None:
    """After 5:00, passive income alone is 480; farm gold is tracked separately on ``SimResult``."""
    t_five_min = 5.0 * 60.0

    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    res = simulate_farm_horizon(
        ch["lux"],
        FarmMode.LANE,
        items,
        [None] * 6,
        t_five_min,
        lane_minion=units["lane_melee"],
        dt=1.0,
    )
    assert res.passive_gold_total == pytest.approx(PASSIVE_GOLD_AT_5MIN, rel=0.0, abs=0.02)
    assert res.passive_gold_total == pytest.approx(480.0, rel=0.0, abs=0.02)
    assert res.total_farm_gold > 0.0
    assert res.passive_gold_total + res.total_farm_gold == pytest.approx(
        res.final_wallet - STARTING_GOLD,
        rel=0.0,
        abs=0.02,
    )


def test_five_minute_jungle_passive_matches_lane_passive() -> None:
    """Passive accrual does not depend on farm mode; only ``passive_gold_over_interval`` applies."""
    t_five_min = 5.0 * 60.0

    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    lane_res = simulate_farm_horizon(
        ch["lux"],
        FarmMode.LANE,
        items,
        [None] * 6,
        t_five_min,
        lane_minion=units["lane_melee"],
        dt=1.0,
    )
    jungle_res = simulate_farm_horizon(
        ch["lux"],
        FarmMode.JUNGLE,
        items,
        [None] * 6,
        t_five_min,
        jungle_monster=units["raptor_small"],
        dt=1.0,
    )
    assert lane_res.passive_gold_total == pytest.approx(jungle_res.passive_gold_total, abs=0.02)
    assert lane_res.passive_gold_total == pytest.approx(480.0, abs=0.02)


def test_three_minute_buy_order_passive_matches_horizon() -> None:
    """``simulate_with_buy_order`` uses the same passive tick as horizon sim (no buys)."""
    t_three_min = 3.0 * 60.0
    expected_passive = PASSIVE_GOLD_PER_SEC * t_three_min

    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    res = simulate_with_buy_order(
        ch["lux"],
        FarmMode.LANE,
        items,
        (),
        t_three_min,
        lane_minion=units["lane_melee"],
        dt=1.0,
    )
    assert res.passive_gold_total == pytest.approx(expected_passive, abs=0.02)
    assert res.gold_spent == 0.0
