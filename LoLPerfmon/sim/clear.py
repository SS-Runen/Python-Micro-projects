from __future__ import annotations

from .data_loader import GameDataBundle, WaveComposition
from .models import ChampionProfile
from .stats import StatBlock


def lane_clear_dps(profile: ChampionProfile, level: int, stats: StatBlock) -> float:
    """
    Modeled damage rate used for minion wave / jungle clear time.

    **Ability damage** uses :class:`~LoLPerfmon.sim.spell_farm_model.SpellFarmCoefficients`
    when parsed from Data Dragon (``effect`` / ``vars``), plus optional kit fallbacks when
    AP/AD scaling is missing from JSON. **Auto-attack** contribution is
    ``auto_attack_clear_weight * as_weight * attack_speed * attack_damage`` (often zero for
    mages). If no spell model exists, falls back to linear :class:`KitParams` weights.
    """
    k = profile.kit
    ah_part = k.ah_weight * stats.ability_haste
    auto_part = k.auto_attack_clear_weight * k.as_weight * stats.attack_speed * stats.attack_damage

    sf = profile.spell_farm
    if sf is not None and sf.lines:
        spell_part = sf.rotation_ability_dps(level, stats.ability_power, stats.attack_damage)
        if sf.needs_kit_ap_fallback:
            spell_part += k.ap_weight * stats.ability_power
        if sf.needs_kit_ad_fallback:
            spell_part += k.ad_weight * stats.attack_damage
        return spell_part + ah_part + auto_part

    return (
        k.base_ability_dps
        + k.ad_weight * stats.attack_damage
        + k.ap_weight * stats.ability_power
        + auto_part
        + ah_part
    )


def effective_dps(profile: ChampionProfile, level: int, stats: StatBlock) -> float:
    """Alias for :func:`lane_clear_dps` (same signature)."""
    return lane_clear_dps(profile, level, stats)


def wave_hp_budget(wave: WaveComposition, game_minute: float, data: GameDataBundle) -> float:
    h = 0.0
    h += wave.melee * data.hp_for_minion("melee", game_minute)
    h += wave.caster * data.hp_for_minion("caster", game_minute)
    h += wave.siege * data.hp_for_minion("siege", game_minute)
    return h


def wave_gold_if_full_clear(wave: WaveComposition, game_minute: float, data: GameDataBundle) -> float:
    g = 0.0
    g += wave.melee * data.gold_for_kill("melee", game_minute)
    g += wave.caster * data.gold_for_kill("caster", game_minute)
    g += wave.siege * data.gold_for_kill("siege", game_minute)
    return g


def clear_time_seconds(
    wave: WaveComposition, game_minute: float, data: GameDataBundle, clear_dps: float
) -> float:
    hp = wave_hp_budget(wave, game_minute, data)
    return hp / max(clear_dps, 1e-6)


def throughput_ratio(clear_time: float, wave_interval: float) -> float:
    """Fraction of a wave cleared if fights repeat every wave_interval."""
    return min(1.0, wave_interval / max(clear_time, 1e-9))


def jungle_cycle_seconds(
    profile: ChampionProfile, level: int, stats: StatBlock, data: GameDataBundle
) -> float:
    dps = effective_dps(profile, level, stats)
    base = data.rules.jungle_base_cycle_seconds
    ref = 80.0
    return base * ref / max(dps, 1e-6)
