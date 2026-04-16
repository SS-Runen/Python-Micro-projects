from __future__ import annotations

from LoLPerfmon.data.loaders import data_root_default, load_items_dir
from LoLPerfmon.sim.item_progression import combine_gold_cost


def test_combine_gold_cost_lost_chapter():
    root = data_root_default()
    items = load_items_dir(root / "items")
    lc = items["lost_chapter"]
    assert combine_gold_cost(lc, items) == 200.0
    assert combine_gold_cost(items["amplifying_tome"], items) == 400.0


def test_combine_gold_cost_nonnegative():
    root = data_root_default()
    items = load_items_dir(root / "items")
    lc = items["lost_chapter"]
    assert combine_gold_cost(lc, items) >= 0.0
