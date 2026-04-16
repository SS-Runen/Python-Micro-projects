from pathlib import Path

from LoLPerfmon.data.loaders import data_root_default, load_bundle


def test_load_bundle():
    root = data_root_default()
    ch, items, units, graph = load_bundle(root)
    assert "lux" in ch
    assert "amplifying_tome" in items
    assert "lane_melee" in units
