"""Spell rotation farm model: Data Dragon effect/vars drive ability clear DPS."""

from __future__ import annotations

from LoLPerfmon.sim.clear import lane_clear_dps
from LoLPerfmon.sim.ddragon_fetch import champion_profile_from_ddragon
from LoLPerfmon.sim.ddragon_sample_payloads import LUX_CHAMPION_EXCERPT
from LoLPerfmon.sim.models import ItemDef, StatBonus
from LoLPerfmon.sim.stats import total_stats


def test_lux_profile_has_spell_farm_and_scales_ap_not_pure_ad_item() -> None:
    p = champion_profile_from_ddragon("lux", LUX_CHAMPION_EXCERPT)
    assert p.spell_farm is not None
    assert p.spell_farm.lines
    items = {
        "ap": ItemDef(id="ap", name="ap", total_cost=100.0, stats=StatBonus(ability_power=40.0), from_ids=()),
        "ad": ItemDef(id="ad", name="ad", total_cost=100.0, stats=StatBonus(attack_damage=40.0), from_ids=()),
    }
    st_ap = total_stats(p, 11, ("ap",), items)
    st_ad = total_stats(p, 11, ("ad",), items)
    d_ap = lane_clear_dps(p, 11, st_ap)
    d_ad = lane_clear_dps(p, 11, st_ad)
    assert d_ap > d_ad + 1e-6


def test_spell_farm_from_champion_data_none_when_no_damage_rows() -> None:
    from LoLPerfmon.sim.ddragon_spell_parse import parse_champion_spells
    from LoLPerfmon.sim.spell_farm_model import spell_farm_from_champion_data

    raw = {"spells": [], "passive": {}}
    sd = parse_champion_spells("x", raw)
    assert spell_farm_from_champion_data(sd) is None
