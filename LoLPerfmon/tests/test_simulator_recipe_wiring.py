from __future__ import annotations

import pytest

from LoLPerfmon.data.loaders import data_root_default, load_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.simulator import simulate_with_buy_order


def test_buy_order_combine_after_components(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("LoLPerfmon.sim.simulator.STARTING_GOLD", 10_000.0)
    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    order = (
        "amplifying_tome",
        "sapphire_crystal",
        "glowing_mote",
        "lost_chapter",
    )
    res = simulate_with_buy_order(
        ch["lux"],
        FarmMode.LANE,
        items,
        order,
        120.0,
        lane_minion=units["lane_melee"],
    )
    assert res.gold_spent == pytest.approx(1200.0)
    assert res.final_inventory is not None
    assert list(res.final_inventory).count("lost_chapter") == 1
    assert sum(1 for s in res.final_inventory if s is not None) == 1


def test_buy_order_full_purchase_lost_chapter_without_components(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("LoLPerfmon.sim.simulator.STARTING_GOLD", 10_000.0)
    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    res = simulate_with_buy_order(
        ch["lux"],
        FarmMode.LANE,
        items,
        ("lost_chapter",),
        60.0,
        lane_minion=units["lane_melee"],
    )
    assert res.gold_spent == pytest.approx(1200.0)
    assert res.final_inventory is not None
    assert res.final_inventory[0] == "lost_chapter"
