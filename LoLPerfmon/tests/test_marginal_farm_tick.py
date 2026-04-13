"""Capped-throughput marginal farm tick derivatives (scipy/numpy)."""

from __future__ import annotations

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.marginal_farm_tick import jungle_tick_gold_derivative_wrt_dps


def test_jungle_tick_derivative_near_zero_when_route_efficiency_capped() -> None:
    """eff = min(1, dps/80); for large dps the gold tick is flat in dps (derivative ~ 0)."""
    data = build_offline_bundle()
    g = jungle_tick_gold_derivative_wrt_dps(5000.0, data.rules)
    assert abs(g) < 1e-3
