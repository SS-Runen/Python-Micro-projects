"""Summoner's Rift (Data Dragon maps['11']) filter — wiki Classic SR 5v5 alignment."""

from __future__ import annotations

from LoLPerfmon.sim.ddragon_fetch import (
    item_def_from_ddragon_entry,
    item_on_summoners_rift_classic,
)


def test_item_on_summoners_rift_classic_requires_map_11() -> None:
    assert item_on_summoners_rift_classic({"maps": {"11": True}}) is True
    assert item_on_summoners_rift_classic({"maps": {"11": False, "12": True}}) is False
    assert item_on_summoners_rift_classic({}) is False


def test_item_def_skips_non_sr_items() -> None:
    base = {"gold": {"total": 100}, "name": "Test", "stats": {}}
    ha_only = {**base, "maps": {"11": False, "12": True}}
    assert item_def_from_ddragon_entry("999", ha_only) is None
    sr = {**base, "maps": {"11": True, "12": True}}
    ent = item_def_from_ddragon_entry("999", sr)
    assert ent is not None
    assert ent.total_cost == 100.0
