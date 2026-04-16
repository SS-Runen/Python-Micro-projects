from __future__ import annotations

import pytest

from LoLPerfmon.data.loaders import data_root_default, load_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.simulator import simulate_with_buy_order
from LoLPerfmon.sim.search import BeamSearchConfig, beam_search_farm_build


def test_beam_search_smoke_recipe_prefix(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("LoLPerfmon.sim.simulator.STARTING_GOLD", 10_000.0)
    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    candidates = (
        "amplifying_tome",
        "sapphire_crystal",
        "glowing_mote",
        "lost_chapter",
    )
    prefix, _score, res = beam_search_farm_build(
        ch["lux"],
        FarmMode.LANE,
        items,
        candidates,
        lane_minion=units["lane_melee"],
        jungle_monster=None,
        cfg=BeamSearchConfig(
            beam_width=4,
            max_depth=4,
            max_leaf_evals=64,
            t_max=120.0,
        ),
    )
    assert isinstance(prefix, tuple)
    assert res.gold_spent >= 0
    direct = simulate_with_buy_order(
        ch["lux"],
        FarmMode.LANE,
        items,
        prefix,
        120.0,
        lane_minion=units["lane_melee"],
    )
    assert res.gold_spent == pytest.approx(direct.gold_spent)
