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


def test_lux_modeled_spell_dps_increases_with_ability_haste() -> None:
    """Ability haste shortens spell cooldowns in :meth:`SpellFarmCoefficients.rotation_ability_dps`."""
    p = champion_profile_from_ddragon("lux", LUX_CHAMPION_EXCERPT)
    assert p.spell_farm is not None
    items = {
        "ah": ItemDef(
            id="ah",
            name="ah",
            total_cost=100.0,
            stats=StatBonus(ability_haste=30.0),
            from_ids=(),
        ),
    }
    st0 = total_stats(p, 11, (), items)
    st1 = total_stats(p, 11, ("ah",), items)
    assert st0.ability_haste == 0.0
    assert st1.ability_haste == 30.0
    d0 = lane_clear_dps(p, 11, st0)
    d1 = lane_clear_dps(p, 11, st1)
    assert d1 > d0 + 1e-6


def test_bonus_ad_only_scaling_uses_bonus_attack_damage() -> None:
    from LoLPerfmon.sim.spell_farm_model import SpellFarmCoefficients, SpellLine

    z5 = (0.0, 0.0, 0.0, 0.0, 0.0)
    b5 = (0.5, 0.5, 0.5, 0.5, 0.5)
    dead = SpellLine(
        cooldown=1e6,
        base_by_rank=(),
        ap_total_by_rank=z5,
        ap_bonus_by_rank=z5,
        ad_total_by_rank=z5,
        ad_bonus_by_rank=z5,
        max_rank=5,
    )
    dead_r = SpellLine(
        cooldown=1e6,
        base_by_rank=(),
        ap_total_by_rank=z5,
        ap_bonus_by_rank=z5,
        ad_total_by_rank=z5,
        ad_bonus_by_rank=z5,
        max_rank=3,
        is_ultimate=True,
    )
    line = SpellLine(
        cooldown=4.0,
        base_by_rank=(),
        ap_total_by_rank=z5,
        ap_bonus_by_rank=z5,
        ad_total_by_rank=z5,
        ad_bonus_by_rank=b5,
        max_rank=5,
    )
    sf = SpellFarmCoefficients(
        lines=(line, dead, dead, dead_r),
        needs_kit_ap_fallback=False,
        needs_kit_ad_fallback=False,
    )
    d_low = sf.rotation_ability_dps(11, 0.0, 0.0, 80.0, 20.0, 0.0)
    d_high = sf.rotation_ability_dps(11, 0.0, 0.0, 60.0, 40.0, 0.0)
    assert d_high > d_low + 1e-9


def test_optimal_skill_points_sum_to_champion_level() -> None:
    from LoLPerfmon.sim.spell_farm_model import (
        SpellFarmCoefficients,
        SpellLine,
        max_skill_points_for_ultimate,
    )

    z5 = (0.1,) * 5
    line = SpellLine(
        cooldown=5.0,
        base_by_rank=(),
        ap_total_by_rank=z5,
        ap_bonus_by_rank=z5,
        ad_total_by_rank=z5,
        ad_bonus_by_rank=z5,
        max_rank=5,
    )
    ult = SpellLine(
        cooldown=5.0,
        base_by_rank=(),
        ap_total_by_rank=z5,
        ap_bonus_by_rank=z5,
        ad_total_by_rank=z5,
        ad_bonus_by_rank=z5,
        max_rank=3,
        is_ultimate=True,
    )
    sf = SpellFarmCoefficients(
        lines=(line, line, line, ult),
        needs_kit_ap_fallback=False,
        needs_kit_ad_fallback=False,
    )
    for lv in (1, 6, 11, 18):
        r = sf.optimal_waveclear_rank_allocation(lv, 50.0, 0.0, 60.0, 0.0, 0.0)
        assert sum(r) == min(lv, 5 + 5 + 5 + 3)
        assert r[3] <= max_skill_points_for_ultimate(lv)
    r5 = sf.optimal_waveclear_rank_allocation(5, 50.0, 0.0, 60.0, 0.0, 0.0)
    assert r5[3] == 0


def test_statblock_bonus_matches_intrinsic_base() -> None:
    from LoLPerfmon.sim.models import ChampionProfile, KitParams

    p = ChampionProfile(
        id="t",
        base_health=500.0,
        growth_health=0.0,
        base_mana=400.0,
        growth_mana=0.0,
        base_attack_damage=60.0,
        growth_attack_damage=0.0,
        base_ability_power=0.0,
        growth_ability_power=0.0,
        base_armor=25.0,
        growth_armor=0.0,
        base_magic_resist=30.0,
        growth_magic_resist=0.0,
        base_attack_speed=0.65,
        attack_speed_ratio=0.625,
        bonus_attack_speed_growth=0.0,
        kit=KitParams(),
        spell_farm=None,
    )
    items: dict = {}
    st = total_stats(p, 5, (), items)
    assert st.bonus_attack_damage == 0.0
    assert st.bonus_ability_power == 0.0


def test_spell_farm_from_champion_data_none_when_no_damage_rows() -> None:
    from LoLPerfmon.sim.ddragon_spell_parse import parse_champion_spells
    from LoLPerfmon.sim.spell_farm_model import spell_farm_from_champion_data

    raw = {"spells": [], "passive": {}}
    sd = parse_champion_spells("x", raw)
    assert spell_farm_from_champion_data(sd) is None
