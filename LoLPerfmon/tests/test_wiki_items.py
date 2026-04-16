from pathlib import Path

import pytest

from LoLPerfmon.data.loaders import data_root_default, load_bundle, load_items_dir
from LoLPerfmon.ingest.normalizer import ddragon_item_to_record, merge_item_wiki_ddragon_allowlist
from LoLPerfmon.ingest.wiki_items import (
    normalize_item_display_name,
    parse_wiki_item_list_grid,
    try_wiki_sr_allowlist,
)
from LoLPerfmon.sim.combat_throughput import sum_item_stats
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.item_progression import combine_gold_cost, complete_recipe_in_inventory
from LoLPerfmon.sim.simulator import simulate_with_buy_order

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "wiki_list_items_snippet.html"


def test_normalize_item_display_name_apostrophe() -> None:
    assert normalize_item_display_name("Guardian\u2019s Blade") == normalize_item_display_name("Guardian's Blade")


def test_parse_wiki_item_list_grid_classic_sr_filter() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    r = parse_wiki_item_list_grid(html)
    assert "amplifying tome" in r.allowlist_normalized
    assert "guardian's blade" not in r.allowlist_normalized
    assert "empty modes row" not in r.allowlist_normalized
    assert "turret junk" not in r.allowlist_normalized
    assert r.excluded_by_mode >= 2


def test_parse_wiki_item_list_grid_section_exclusion_counts() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    r = parse_wiki_item_list_grid(html)
    assert r.excluded_by_section >= 1


def test_merge_item_wiki_ddragon_allowlist_filters_and_discrepancies() -> None:
    data_obj = {
        "1052": {
            "name": "Amplifying Tome",
            "gold": {"total": 400},
            "stats": {},
            "from": [],
            "into": [],
        },
        "1001": {
            "name": "Boots",
            "gold": {"total": 300},
            "stats": {},
            "from": [],
            "into": [],
        },
    }
    allow = {"amplifying tome", "boots", "wiki_only_name"}
    merged, disc = merge_item_wiki_ddragon_allowlist(
        data_obj,
        allow,
        wiki_ok=True,
        wiki_fallback=False,
        patch="15.1.1",
        wiki_list_url="https://wiki.example/List",
    )
    assert set(merged.keys()) == {"1052", "1001"}
    wiki_only = {d.entity_id for d in disc if d.delta_kind == "missing"}
    assert "wiki_only_name" in wiki_only


def test_merge_item_wiki_ddragon_fallback_all_items() -> None:
    data_obj = {
        "1": {"name": "A", "gold": {"total": 1}, "stats": {}, "from": [], "into": []},
    }
    merged, disc = merge_item_wiki_ddragon_allowlist(
        data_obj,
        None,
        wiki_ok=False,
        wiki_fallback=True,
        patch="p",
    )
    assert "1" in merged
    assert merged["1"]["source_provenance"].get("wiki_fallback") is True
    assert disc == []


def test_try_wiki_sr_allowlist_scrapes_allowlist_from_html(monkeypatch: pytest.MonkeyPatch) -> None:
    html = FIXTURE.read_text(encoding="utf-8")

    def _fake_fetch(url: str) -> str:
        return html

    monkeypatch.setattr(
        "LoLPerfmon.ingest.wiki_items.fetch_wiki_list_of_items_html",
        _fake_fetch,
    )
    step = try_wiki_sr_allowlist(skip_wiki=False, list_url="https://example.invalid/List")
    assert step.wiki_ok
    assert not step.wiki_fallback
    assert step.allowlist_normalized is not None
    assert "amplifying tome" in step.allowlist_normalized
    assert step.last_error is None
    assert step.entries_parsed >= 1


def test_try_wiki_sr_allowlist_fetch_failure_uses_ddragon_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(url: str) -> str:
        raise OSError("simulated network failure")

    monkeypatch.setattr("LoLPerfmon.ingest.wiki_items.fetch_wiki_list_of_items_html", _boom)
    step = try_wiki_sr_allowlist(skip_wiki=False, list_url="https://example.invalid/List")
    assert not step.wiki_ok
    assert step.wiki_fallback
    assert step.allowlist_normalized is None
    assert step.last_error == "simulated network failure"


def test_try_wiki_sr_allowlist_skip_wiki_uses_ddragon_fallback() -> None:
    step = try_wiki_sr_allowlist(skip_wiki=True, list_url="https://example.invalid/List")
    assert not step.wiki_ok
    assert step.wiki_fallback
    assert step.allowlist_normalized is None
    assert step.last_error is None


def test_wiki_join_preserves_ddragon_stats_recipe_fields() -> None:
    raw = {
        "name": "Test Rod",
        "gold": {"total": 850},
        "stats": {"FlatMagicDamageMod": 60.0},
        "from": ["1"],
        "into": ["2"],
    }
    iid = "99"
    pure = ddragon_item_to_record(iid, raw)
    allow = {normalize_item_display_name("Test Rod")}
    merged, disc = merge_item_wiki_ddragon_allowlist(
        {iid: raw},
        allow,
        wiki_ok=True,
        wiki_fallback=False,
        patch="1.0.0",
        wiki_list_url="https://wiki.example/List",
    )
    assert disc == []
    assert merged[iid]["stats_granted"] == pure["stats_granted"]
    assert merged[iid]["cost"] == pure["cost"]
    assert merged[iid]["builds_from"] == pure["builds_from"]
    assert merged[iid]["builds_into"] == pure["builds_into"]
    assert merged[iid]["name"] == pure["name"]


def test_lux_lost_chapter_inventory_economy_and_sim_still_coherent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: Wiki allowlist only gates *which* items are written; sim uses the same ItemStatic shape."""
    monkeypatch.setattr("LoLPerfmon.sim.simulator.STARTING_GOLD", 10_000.0)
    root = data_root_default()
    items = load_items_dir(root / "items")
    ch, bundle_items, units, _ = load_bundle(root)
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
    assert sum_item_stats(new_inv, items) == {
        "ability_power": 40.0,
        "mana": 300.0,
        "ability_haste": 10.0,
    }
    lc = items["lost_chapter"]
    assert combine_gold_cost(lc, items) == 200.0
    assert combine_gold_cost(items["amplifying_tome"], items) == 400.0
    res = simulate_with_buy_order(
        ch["lux"],
        FarmMode.LANE,
        bundle_items,
        (
            "amplifying_tome",
            "sapphire_crystal",
            "glowing_mote",
            "lost_chapter",
        ),
        120.0,
        lane_minion=units["lane_melee"],
    )
    assert res.final_inventory is not None
    assert list(res.final_inventory).count("lost_chapter") == 1
