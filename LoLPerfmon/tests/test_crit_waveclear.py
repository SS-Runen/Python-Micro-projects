from __future__ import annotations

from LoLPerfmon.sim.clear import lane_clear_dps
from LoLPerfmon.sim.models import ChampionProfile, KitParams
from LoLPerfmon.sim.stats import StatBlock


def _auto_only_profile() -> ChampionProfile:
    return ChampionProfile(
        id="auto_only",
        base_health=600.0,
        growth_health=100.0,
        base_mana=0.0,
        growth_mana=0.0,
        base_attack_damage=60.0,
        growth_attack_damage=3.0,
        base_ability_power=0.0,
        growth_ability_power=0.0,
        base_armor=30.0,
        growth_armor=4.0,
        base_magic_resist=30.0,
        growth_magic_resist=1.3,
        base_attack_speed=0.7,
        attack_speed_ratio=0.7,
        bonus_attack_speed_growth=0.02,
        kit=KitParams(
            ad_weight=0.0,
            ap_weight=0.0,
            as_weight=1.0,
            ah_weight=0.0,
            base_ability_dps=0.0,
            auto_attack_clear_weight=1.0,
        ),
    )


def test_lane_clear_dps_uses_expected_crit_damage_on_autos() -> None:
    p = _auto_only_profile()
    base = StatBlock(
        attack_damage=100.0,
        ability_power=0.0,
        bonus_attack_damage=0.0,
        bonus_ability_power=0.0,
        attack_speed=1.0,
        ability_haste=0.0,
        health=600.0,
        mana=0.0,
        armor=30.0,
        magic_resist=30.0,
        crit_chance=0.0,
        crit_damage_bonus=0.0,
    )
    with_crit = StatBlock(
        attack_damage=100.0,
        ability_power=0.0,
        bonus_attack_damage=0.0,
        bonus_ability_power=0.0,
        attack_speed=1.0,
        ability_haste=0.0,
        health=600.0,
        mana=0.0,
        armor=30.0,
        magic_resist=30.0,
        crit_chance=1.0,
        crit_damage_bonus=0.0,
    )
    d0 = lane_clear_dps(p, 11, base)
    d1 = lane_clear_dps(p, 11, with_crit)
    assert abs(d0 - 100.0) < 1e-9
    assert abs(d1 - 175.0) < 1e-9
