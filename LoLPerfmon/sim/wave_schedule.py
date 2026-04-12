"""Lane wave composition from SR spawn cadence (no committed per-wave JSON)."""

from __future__ import annotations

from .data_loader import WaveComposition


def generate_lane_waves_until(
    t_max_seconds: float,
    first_spawn_s: float,
    interval_s: float,
) -> list[WaveComposition]:
    """
    Standard lane minions: 3 melee + 3 caster each wave; siege on a repeating cadence
    after the early waves (simplified SR model).
    """
    waves: list[WaveComposition] = []
    k = 0
    while True:
        t = first_spawn_s + k * interval_s
        if t > t_max_seconds:
            break
        melee, caster = 3, 3
        siege = 1 if k >= 2 and (k - 2) % 3 == 0 else 0
        waves.append(WaveComposition(wave_index=k, melee=melee, caster=caster, siege=siege))
        k += 1
    return waves
