from __future__ import annotations

import json
from pathlib import Path

import pytest

from LoLPerfmon.ingest.champion_sync import build_champion_record
from LoLPerfmon.ingest.normalizer import ddragon_champion_to_record, merge_champion_wiki_ddragon
from LoLPerfmon.ingest.sources import resolve_ddragon_champion_key
from LoLPerfmon.ingest.wiki_parser import (
    normalize_champion_id,
    parse_champion_list_table,
    parse_wiki_champion_detail_stats,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_parse_champion_list_table_filters_rows():
    html = (FIXTURES / "wiki_list_champions.html").read_text(encoding="utf-8")
    rows = parse_champion_list_table(html)
    assert len(rows) == 2
    slugs = {r.wiki_slug for r in rows}
    assert slugs == {"Aatrox", "Lux"}
    assert rows[1].champion_id == "lux"


def test_parse_wiki_champion_detail_stats():
    html = (FIXTURES / "wiki_lux_lol.html").read_text(encoding="utf-8")
    w = parse_wiki_champion_detail_stats(html)
    assert w["base_stats_at_level1"]["attack_damage"] == 54.0
    assert w["growth_per_level"]["attack_damage"] == 3.3
    assert "attack_damage" in w["parsed_fields"]


def test_normalize_champion_id_leesin():
    assert normalize_champion_id("Lee Sin") == "leesin"
    assert normalize_champion_id("Lee_Sin") == "leesin"


def test_resolve_ddragon_champion_key():
    idx = {"data": {"Lux": {"id": "Lux"}, "MonkeyKing": {"id": "MonkeyKing"}}}
    assert resolve_ddragon_champion_key(idx, "lux") == "Lux"
    assert resolve_ddragon_champion_key(idx, "monkeyking") == "MonkeyKing"


def test_ddragon_champion_to_record_min_fixture():
    raw = json.loads((FIXTURES / "dd_lux_min.json").read_text(encoding="utf-8"))
    rec = ddragon_champion_to_record(raw, "Lux", patch="test", source_url="http://example.invalid")
    assert rec["champion_id"] == "lux"
    assert rec["base_stats_at_level1"]["attack_damage"] == 50.0
    assert rec["growth_per_level"]["attack_speed"] == pytest.approx(0.02)


def test_merge_champion_wiki_ddragon_conflict():
    dd = {
        "champion_id": "lux",
        "name": "Lux",
        "role_modes_allowed": ["lane", "jungle"],
        "base_stats_at_level1": {"attack_damage": 50.0, "ability_power": 0.0, "attack_speed": 0.65},
        "growth_per_level": {"attack_damage": 3.0, "ability_power": 0.0, "attack_speed": 0.02},
        "ability_scaling_profile": {"primary_axis": "ap"},
        "clear_profile_tags": ["ap"],
    }
    wiki = {
        "base_stats_at_level1": {"attack_damage": 54.0},
        "growth_per_level": {"attack_damage": 3.3},
        "parsed_fields": ["attack_damage"],
    }
    merged, disc = merge_champion_wiki_ddragon(dd, wiki, prefer_dd_on_conflict=False)
    assert merged["base_stats_at_level1"]["attack_damage"] == 54.0
    assert len(disc) == 1
    merged_dd, _ = merge_champion_wiki_ddragon(dd, wiki, prefer_dd_on_conflict=True)
    assert merged_dd["base_stats_at_level1"]["attack_damage"] == 50.0


def test_build_champion_record_offline_no_network():
    list_html = (FIXTURES / "wiki_list_champions.html").read_text(encoding="utf-8")
    wiki_detail = (FIXTURES / "wiki_lux_lol.html").read_text(encoding="utf-8")
    dd = json.loads((FIXTURES / "dd_lux_min.json").read_text(encoding="utf-8"))
    idx = {"data": {"Lux": {"id": "Lux", "key": "99", "name": "Lux"}}}
    rec = build_champion_record(
        "lux",
        patch="99.99.99",
        list_html=list_html,
        wiki_detail_html=wiki_detail,
        champion_index=idx,
        full_champion_json=dd,
    )
    assert rec["champion_id"] == "lux"
    assert rec["base_stats_at_level1"]["attack_damage"] == 54.0
