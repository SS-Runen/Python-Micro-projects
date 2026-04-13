"""Finite-difference stability smoke tests for marginal farm tick derivatives (timestep-resolution plan)."""

from __future__ import annotations

import numpy as np

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.marginal_farm_tick import (
    jungle_tick_gold_derivative_wrt_dps,
    lane_tick_gold_derivative_wrt_dps,
)
from LoLPerfmon.sim.wave_schedule import wave_composition_at_index


def test_lane_tick_gold_derivative_finite_and_stable_band() -> None:
    data = build_offline_bundle(lane_horizon_seconds=120.0)
    wave = wave_composition_at_index(0)
    gm = data.rules.first_wave_spawn_seconds / 60.0
    dps0 = 80.0
    g0 = lane_tick_gold_derivative_wrt_dps(dps0, wave, gm, data, 1.0)
    g1 = lane_tick_gold_derivative_wrt_dps(dps0 * 1.01, wave, gm, data, 1.0)
    assert np.isfinite(g0) and np.isfinite(g1)
    if abs(g0) > 1e-12:
        assert abs(g1 - g0) / abs(g0) < 0.5


def test_jungle_tick_gold_derivative_finite() -> None:
    data = build_offline_bundle()
    dps0 = 120.0
    j0 = jungle_tick_gold_derivative_wrt_dps(dps0, data.rules)
    assert np.isfinite(j0)
