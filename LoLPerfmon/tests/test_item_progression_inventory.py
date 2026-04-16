from __future__ import annotations

from LoLPerfmon.data.loaders import data_root_default, load_items_dir
from LoLPerfmon.sim.combat_throughput import sum_item_stats
from LoLPerfmon.sim.item_progression import complete_recipe_in_inventory


def test_lost_chapter_recipe_slots_and_stats():
    root = data_root_default()
    items = load_items_dir(root / "items")
    inv = [
        "amplifying_tome",
        "sapphire_crystal",
        "glowing_mote",
        None,
        None,
        None,
    ]
    assert sum_item_stats(inv, items) == {
        "ability_power": 20.0,
        "mana": 300.0,
        "ability_haste": 5.0,
    }
    new_inv = complete_recipe_in_inventory(inv, items, "lost_chapter")
    assert new_inv.count("lost_chapter") == 1
    assert sum(1 for s in new_inv if s is not None) == 1
    assert sum_item_stats(new_inv, items) == {
        "ability_power": 40.0,
        "mana": 300.0,
        "ability_haste": 10.0,
    }
