from __future__ import annotations

from .data_loader import GameDataBundle, WaveComposition
from .models import ChampionProfile
from .stats import StatBlock


def effective_dps(profile: ChampionProfile, stats: StatBlock) -> float:
    k = profile.kit
    return (
        k.base_ability_dps
        + k.ad_weight * stats.attack_damage
        + k.ap_weight * stats.ability_power
        + k.as_weight * stats.attack_speed * stats.attack_damage
        + k.ah_weight * stats.ability_haste
    )


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


def clear_time_seconds(wave: WaveComposition, game_minute: float, data: GameDataBundle, dps: float) -> float:
    hp = wave_hp_budget(wave, game_minute, data)
    return hp / max(dps, 1e-6)


def throughput_ratio(clear_time: float, wave_interval: float) -> float:
    """Fraction of a wave cleared if fights repeat every wave_interval."""
    return min(1.0, wave_interval / max(clear_time, 1e-9))


def jungle_cycle_seconds(profile: ChampionProfile, stats: StatBlock, data: GameDataBundle) -> float:
    dps = effective_dps(profile, stats)
    base = data.rules.jungle_base_cycle_seconds
    ref = 80.0
    return base * ref / max(dps, 1e-6)
