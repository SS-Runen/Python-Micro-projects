from __future__ import annotations

import logging

import pytest

from LoLPerfmon.data.loaders import data_root_default, load_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.sim_logging import PeriodicSimLog
from LoLPerfmon.sim.simulator import simulate_with_buy_order


def test_periodic_sim_log_fires_at_interval() -> None:
    n = 0
    pl = PeriodicSimLog(10.0)

    def emit() -> None:
        nonlocal n
        n += 1

    pl.after_time_step(9.0, emit)
    assert n == 0
    pl.after_time_step(10.0, emit)
    assert n == 1
    pl.after_time_step(20.0, emit)
    assert n == 2


def test_simulate_with_buy_order_emits_decile_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "LoLPerfmon.sim")
    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    simulate_with_buy_order(
        ch["lux"],
        FarmMode.LANE,
        items,
        (),
        35.0,
        lane_minion=units["lane_melee"],
        log_interval_sec=10.0,
    )
    assert any("t=10.0s" in r.message for r in caplog.records)
    assert any("sim_buy_order_start" in r.message for r in caplog.records)
