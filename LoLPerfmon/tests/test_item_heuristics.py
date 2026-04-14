"""Layered wave-clear catalog heuristics."""

from __future__ import annotations

from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.item_heuristics import (
    DEFAULT_WAVECLEAR_EXCLUDE_TAGS,
    downward_recipe_closure,
    filter_waveclear_item_catalog,
    modeled_dps_uplift_per_gold,
    rank_item_ids_by_dps_uplift_per_gold,
)
from LoLPerfmon.sim.models import ChampionProfile, ItemDef, KitParams, StatBonus


def _profile() -> ChampionProfile:
    return ChampionProfile(
        id="test_ap",
        base_health=500.0,
        growth_health=0.0,
        base_mana=400.0,
        growth_mana=0.0,
        base_attack_damage=50.0,
        growth_attack_damage=0.0,
        base_ability_power=0.0,
        growth_ability_power=0.0,
        base_armor=20.0,
        growth_armor=0.0,
        base_magic_resist=30.0,
        growth_magic_resist=0.0,
        base_attack_speed=0.625,
        attack_speed_ratio=0.625,
        bonus_attack_speed_growth=0.0,
        kit=KitParams(ap_weight=1.0, ad_weight=0.2, auto_attack_clear_weight=0.0),
        spell_farm=None,
        resource_kind="Mana",
        base_mp_regen=0.0,
        growth_mp_regen=0.0,
    )


def test_downward_recipe_closure_includes_components() -> None:
    full = {
        "c1": ItemDef(id="c1", name="Comp", total_cost=400.0, stats=StatBonus(ability_power=20.0), from_ids=(), into_ids=("parent",)),
        "parent": ItemDef(
            id="parent",
            name="Parent",
            total_cost=800.0,
            stats=StatBonus(ability_power=40.0),
            from_ids=("c1",),
            into_ids=(),
        ),
    }
    out = downward_recipe_closure({"parent"}, full)
    assert set(out.keys()) == {"parent", "c1"}


def test_filter_waveclear_lane_drops_jungle_pet_starter() -> None:
    pet = ItemDef(
        id="pet1",
        name="Pet",
        total_cost=450.0,
        stats=StatBonus(),
        from_ids=(),
        into_ids=(),
        tags=("Jungle",),
    )
    ap_item = ItemDef(
        id="ap1",
        name="AP",
        total_cost=900.0,
        stats=StatBonus(ability_power=40.0),
        from_ids=(),
        into_ids=(),
        tags=("SpellDamage", "Damage"),
    )
    full = {"pet1": pet, "ap1": ap_item}
    out = filter_waveclear_item_catalog(full, FarmMode.LANE, require_tags=frozenset({"SpellDamage"}))
    assert "pet1" not in out
    assert "ap1" in out


def test_default_exclude_tags_contains_support_goldper() -> None:
    assert "Support" in DEFAULT_WAVECLEAR_EXCLUDE_TAGS
    assert "GoldPer" in DEFAULT_WAVECLEAR_EXCLUDE_TAGS


def test_modeled_dps_uplift_per_gold_ap_item_positive() -> None:
    profile = _profile()
    it = ItemDef(
        id="big_ap",
        name="Big AP",
        total_cost=1000.0,
        stats=StatBonus(ability_power=100.0),
        from_ids=(),
        into_ids=(),
        tags=("SpellDamage",),
    )
    items = {"big_ap": it}
    v = modeled_dps_uplift_per_gold(profile, "big_ap", items, level=6)
    assert v > 0.0


def test_rank_item_ids_by_dps_sorts_desc() -> None:
    profile = _profile()
    items = {
        "low": ItemDef(
            id="low",
            name="Low",
            total_cost=500.0,
            stats=StatBonus(ability_power=10.0),
            from_ids=(),
            into_ids=(),
        ),
        "high": ItemDef(
            id="high",
            name="High",
            total_cost=500.0,
            stats=StatBonus(ability_power=80.0),
            from_ids=(),
            into_ids=(),
        ),
    }
    ranked = rank_item_ids_by_dps_uplift_per_gold(profile, items, level=6)
    assert ranked[0][0] == "high"
