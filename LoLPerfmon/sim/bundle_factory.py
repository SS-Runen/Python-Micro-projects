"""
Build :class:`GameDataBundle` from Data Dragon (network) or computed SR defaults (offline).

No JSON seed files are required for the default path.
"""

from __future__ import annotations

from .data_loader import GameDataBundle, GameRules, WaveComposition
from .ddragon_fetch import fetch_champions, fetch_items_for_sim, latest_version
from .minion_defaults import default_minion_economy_tables
from .models import ChampionProfile, ItemDef, KitParams, StatBonus
from .summoners_rift_rules import (
    SR_FIRST_WAVE_SPAWN_SECONDS,
    SR_JUNGLE_BASE_CYCLE_SECONDS,
    SR_JUNGLE_BASE_ROUTE_GOLD,
    SR_JUNGLE_BASE_ROUTE_XP,
    SR_PASSIVE_GOLD_PER_10_SECONDS,
    SR_PASSIVE_GOLD_START_SECONDS,
    SR_STARTING_GOLD,
    SR_WAVE_INTERVAL_SECONDS,
    SR_XP_TO_NEXT_LEVEL,
    default_minion_xp_by_level_tables,
)
from .wave_schedule import generate_lane_waves_until


def _offline_generic_ap_carry() -> ChampionProfile:
    """Archetype AP laner: midpoints within typical SR base-stat ranges (no named champion)."""
    return ChampionProfile(
        id="generic_ap",
        base_health=575.0,
        growth_health=95.0,
        base_mana=400.0,
        growth_mana=25.0,
        base_attack_damage=54.0,
        growth_attack_damage=3.2,
        base_ability_power=0.0,
        growth_ability_power=0.0,
        base_armor=23.0,
        growth_armor=5.0,
        base_magic_resist=30.0,
        growth_magic_resist=1.3,
        base_attack_speed=0.655,
        attack_speed_ratio=0.625,
        bonus_attack_speed_growth=0.028,
        kit=KitParams(ad_weight=0.25, ap_weight=1.1, as_weight=0.15, ah_weight=0.025, base_ability_dps=14.0),
    )


def _offline_placeholder_items() -> dict[str, ItemDef]:
    """Two distinct costs for optimizer tests when Data Dragon is unavailable."""
    return {
        "cheap_ap": ItemDef(
            id="cheap_ap",
            name="Budget AP component (offline)",
            total_cost=400.0,
            stats=StatBonus(ability_power=18.0, health=80.0),
            from_ids=(),
        ),
        "cheap_ad": ItemDef(
            id="cheap_ad",
            name="Budget AD component (offline)",
            total_cost=450.0,
            stats=StatBonus(attack_damage=20.0),
            from_ids=(),
        ),
    }


def _rules(patch_label: str) -> GameRules:
    mxp, cxp, sxp = default_minion_xp_by_level_tables()
    return GameRules(
        patch_version=patch_label,
        first_wave_spawn_seconds=SR_FIRST_WAVE_SPAWN_SECONDS,
        wave_interval_seconds=SR_WAVE_INTERVAL_SECONDS,
        passive_gold_per_10_seconds=SR_PASSIVE_GOLD_PER_10_SECONDS,
        passive_gold_start_seconds=SR_PASSIVE_GOLD_START_SECONDS,
        start_gold=SR_STARTING_GOLD,
        xp_to_next_level=SR_XP_TO_NEXT_LEVEL,
        minion_xp_melee_by_level=mxp,
        minion_xp_caster_by_level=cxp,
        minion_xp_siege_by_level=sxp,
        jungle_base_cycle_seconds=SR_JUNGLE_BASE_CYCLE_SECONDS,
        jungle_base_route_gold=SR_JUNGLE_BASE_ROUTE_GOLD,
        jungle_base_route_xp=SR_JUNGLE_BASE_ROUTE_XP,
    )


def _waves_for_60m() -> list[WaveComposition]:
    return generate_lane_waves_until(3600.0, SR_FIRST_WAVE_SPAWN_SECONDS, SR_WAVE_INTERVAL_SECONDS)


def build_offline_bundle() -> GameDataBundle:
    rules = _rules("offline-computed")
    champs = {"generic_ap": _offline_generic_ap_carry()}
    items = _offline_placeholder_items()
    return GameDataBundle(
        rules=rules,
        champions=champs,
        items=items,
        waves=_waves_for_60m(),
        minion_economy=default_minion_economy_tables(),
        data_dir=None,
    )


def build_bundle_from_ddragon(version: str, timeout: float = 25.0) -> GameDataBundle | None:
    champs = fetch_champions(version, ("Lux", "Karthus", "Quinn"), timeout=timeout)
    items = fetch_items_for_sim(version, timeout=timeout)
    if not champs or len(items) < 1:
        return None
    if len(items) < 2:
        items.update(_offline_placeholder_items())
    rules = _rules(version)
    return GameDataBundle(
        rules=rules,
        champions=champs,
        items=items,
        waves=_waves_for_60m(),
        minion_economy=default_minion_economy_tables(),
        data_dir=None,
    )


def get_game_bundle(offline: bool = False, ddragon_version: str | None = None, timeout: float = 25.0) -> GameDataBundle:
    """
    Preferred entry point: try Data Dragon when ``offline`` is False; otherwise or on
    failure return :func:`build_offline_bundle`.
    """
    if offline:
        return build_offline_bundle()
    ver = ddragon_version or latest_version(timeout=timeout)
    if ver:
        b = build_bundle_from_ddragon(ver, timeout=timeout)
        if b is not None:
            return b
    return build_offline_bundle()


