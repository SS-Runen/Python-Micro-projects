"""
Assertions for frozen Data Dragon excerpts used by :mod:`LoLPerfmon.validation_checks` and pytest.

Keeps validation and unit tests aligned on the same **independent oracles** (arithmetic on
fixture JSON, ``ITEM_STATS_KEYS_MAPPED`` membership), not duplicate copies of implementation
constants for AD/AP weights.
"""

from __future__ import annotations

import math

from .ddragon_availability import ITEM_STATS_KEYS_MAPPED, build_ddragon_audit_report, scan_summoners_rift_item_catalog
from .ddragon_fetch import item_def_from_ddragon_entry, summoners_rift_item_defs_all
from .ddragon_sample_payloads import ITEM_JSON_EXCERPT, LUX_CHAMPION_EXCERPT
from .ddragon_spell_parse import base_ability_dps_hint_from_mean_cooldown, kit_params_from_spells, parse_champion_spells


def assert_unknown_item_stat_is_flagged_unmapped() -> None:
    """1026 carries a nonzero stat key not in the sim mapping — audit must list it."""
    assert "UnknownRiotStat" not in ITEM_STATS_KEYS_MAPPED
    cat = scan_summoners_rift_item_catalog(ITEM_JSON_EXCERPT, "14.23.1")
    assert "1026" in cat.item_ids_unmapped_nonzero_stats


def assert_item_defs_match_fixture_gold_and_mapped_stats() -> None:
    """ItemDef wiring: gold totals and FlatMagicDamageMod → ability_power (not re-stating ItemDef fields)."""
    items = summoners_rift_item_defs_all(ITEM_JSON_EXCERPT)
    raw = ITEM_JSON_EXCERPT["data"]
    assert float(raw["1001"]["gold"]["total"]) == items["1001"].total_cost
    assert float(raw["1026"]["gold"]["total"]) == items["1026"].total_cost
    wand_stats = raw["1026"]["stats"]
    assert isinstance(wand_stats, dict)
    assert items["1026"].stats.ability_power == float(wand_stats["FlatMagicDamageMod"])


def assert_lux_q_cooldown_round_trip_from_fixture() -> None:
    """Parser output matches numeric values in the excerpt (coercion to float)."""
    raw_q = LUX_CHAMPION_EXCERPT["spells"][0]
    data = parse_champion_spells("Lux", LUX_CHAMPION_EXCERPT)
    q = data.spells[0]
    expected = tuple(float(x) for x in raw_q["cooldown"])
    assert q.cooldown == expected


def assert_lux_kit_dps_matches_independent_mean_cooldown() -> None:
    """
    ``base_ability_dps`` must equal the public hook evaluated at the **arithmetic mean**
    of rank cooldowns taken directly from fixture JSON (not from ParsedSpell internals).
    """
    raw_cd = LUX_CHAMPION_EXCERPT["spells"][0]["cooldown"]
    mean_cd = sum(float(x) for x in raw_cd) / len(raw_cd)
    sd = parse_champion_spells("lux", LUX_CHAMPION_EXCERPT)
    kit = kit_params_from_spells("lux", sd)
    want = base_ability_dps_hint_from_mean_cooldown(mean_cd)
    assert math.isclose(kit.base_ability_dps, want), f"got {kit.base_ability_dps}, want {want}"


def assert_audit_report_includes_catalog() -> None:
    rpt = build_ddragon_audit_report("14.23.1", {"lux": LUX_CHAMPION_EXCERPT}, ITEM_JSON_EXCERPT)
    assert rpt.summary_ok
    assert rpt.item_catalog is not None
    assert rpt.item_catalog.total_sr_items == 2


def assert_item_def_skips_items_without_gold() -> None:
    """Regression: entries without ``gold.total`` must not become ItemDef (parser contract)."""
    bad = item_def_from_ddragon_entry("999", {"name": "x", "maps": {"11": True}, "stats": {}})
    assert bad is None


def verify_frozen_sample_payloads() -> None:
    """Single entry point for ``python -m LoLPerfmon.validation_checks``."""
    assert_unknown_item_stat_is_flagged_unmapped()
    assert_item_defs_match_fixture_gold_and_mapped_stats()
    assert_lux_q_cooldown_round_trip_from_fixture()
    assert_lux_kit_dps_matches_independent_mean_cooldown()
    assert_audit_report_includes_catalog()
    assert_item_def_skips_items_without_gold()
