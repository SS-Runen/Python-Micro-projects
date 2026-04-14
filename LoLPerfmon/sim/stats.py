from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .models import ChampionProfile, ItemDef


@dataclass(frozen=True)
class StatDelta:
    attack_damage: float = 0.0
    ability_power: float = 0.0
    bonus_attack_speed_fraction: float = 0.0
    ability_haste: float = 0.0
    health: float = 0.0
    mana: float = 0.0
    armor: float = 0.0
    magic_resist: float = 0.0


@dataclass(frozen=True)
class StatBlock:
    attack_damage: float
    ability_power: float
    #: ``attack_damage`` minus champion intrinsic AD at this level (no items); League-style bonus AD.
    bonus_attack_damage: float
    #: ``ability_power`` minus champion intrinsic AP at this level (no items); used for bonus-AP spell scalings.
    bonus_ability_power: float
    attack_speed: float
    ability_haste: float
    health: float
    mana: float
    armor: float
    magic_resist: float


def clamp_champion_level(level: int) -> int:
    """Clamp simulated champion level to ``[1, 18]`` for stat growth and spell-rank indexing."""
    return max(1, min(18, int(level)))


def growth_stat(base: float, growth: float, bonus_from_items: float, level: int) -> float:
    """
    Primary growth formula (wiki Champion statistic), level >= 1.
    Stat = base + bonus + g * (n-1) * (0.7025 + 0.0175 * (n-1))
    """
    if level < 1:
        raise ValueError("level must be >= 1")
    n = level
    gterm = growth * (n - 1) * (0.7025 + 0.0175 * (n - 1))
    return base + bonus_from_items + gterm


def total_attack_speed(
    base_as: float,
    as_ratio: float,
    bonus_as_growth: float,
    bonus_as_from_items: float,
    level: int,
) -> float:
    """
    Total attack speed = ASbase + [ASbonus + growth_term] * ASratio
    bonus_as_growth is the per-level bonus AS growth stat (fraction, e.g. 0.03).
    """
    if level < 1:
        raise ValueError("level must be >= 1")
    n = level
    growth_term = bonus_as_growth * (n - 1) * (0.7025 + 0.0175 * (n - 1))
    bracket = bonus_as_from_items + growth_term
    return base_as + bracket * as_ratio


def apply_items(items: tuple[ItemDef, ...]) -> StatDelta:
    d = StatDelta()
    for it in items:
        d = StatDelta(
            attack_damage=d.attack_damage + it.stats.attack_damage,
            ability_power=d.ability_power + it.stats.ability_power,
            bonus_attack_speed_fraction=d.bonus_attack_speed_fraction
            + it.stats.bonus_attack_speed_fraction,
            ability_haste=d.ability_haste + it.stats.ability_haste,
            health=d.health + it.stats.health,
            mana=d.mana + it.stats.mana,
            armor=d.armor + it.stats.armor,
            magic_resist=d.magic_resist + it.stats.magic_resist,
        )
    return d


def total_stats(profile: ChampionProfile, level: int, inventory: tuple[str, ...], items_by_id: Mapping[str, ItemDef]) -> StatBlock:
    item_defs = tuple(items_by_id[i] for i in inventory if i in items_by_id)
    delta = apply_items(item_defs)
    ad = growth_stat(profile.base_attack_damage, profile.growth_attack_damage, delta.attack_damage, level)
    ap = growth_stat(profile.base_ability_power, profile.growth_ability_power, delta.ability_power, level)
    hp = growth_stat(profile.base_health, profile.growth_health, delta.health, level)
    mana = growth_stat(profile.base_mana, profile.growth_mana, delta.mana, level)
    ar = growth_stat(profile.base_armor, profile.growth_armor, delta.armor, level)
    mr = growth_stat(profile.base_magic_resist, profile.growth_magic_resist, delta.magic_resist, level)
    ah = delta.ability_haste
    attack_speed = total_attack_speed(
        profile.base_attack_speed,
        profile.attack_speed_ratio,
        profile.bonus_attack_speed_growth,
        delta.bonus_attack_speed_fraction,
        level,
    )
    ad_base = growth_stat(profile.base_attack_damage, profile.growth_attack_damage, 0.0, level)
    ap_base = growth_stat(profile.base_ability_power, profile.growth_ability_power, 0.0, level)
    bonus_ad = max(0.0, ad - ad_base)
    bonus_ap = max(0.0, ap - ap_base)
    return StatBlock(
        attack_damage=ad,
        ability_power=ap,
        bonus_attack_damage=bonus_ad,
        bonus_ability_power=bonus_ap,
        attack_speed=attack_speed,
        ability_haste=ah,
        health=hp,
        mana=mana,
        armor=ar,
        magic_resist=mr,
    )
