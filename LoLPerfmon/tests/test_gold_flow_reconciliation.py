"""Wallet bookkeeping: farm + passive + sells − spent = final."""

from __future__ import annotations

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.greedy_farm_build import stepwise_farm_build
from LoLPerfmon.sim.simulator import PurchasePolicy, gold_flow_reconciliation_error, simulate


def test_gold_flow_reconciliation_offline_lane_greedy() -> None:
    data = build_offline_bundle()
    _order, _farm, res, _meta = stepwise_farm_build(data, "generic_ap", t_max=400.0)
    assert gold_flow_reconciliation_error(res) < 1e-5


def test_gold_flow_reconciliation_offline_simulate_no_hook() -> None:
    data = build_offline_bundle(lane_horizon_seconds=300.0)
    res = simulate(
        data,
        "generic_ap",
        FarmMode.LANE,
        PurchasePolicy(buy_order=()),
        t_max=300.0,
    )
    assert gold_flow_reconciliation_error(res) < 1e-5
    assert res.total_shop_sell_gold == 0.0
