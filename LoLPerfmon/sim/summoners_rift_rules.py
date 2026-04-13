"""
Summoner's Rift Classic 5v5 rule constants (gold cadence, wave timing, XP curve).

These match Riot's published SR behavior described on the League of Legends Wiki
(Gold § Passive gold gain, Farming § wave timing, Experience (champion) § level curve).
They are game rules, not match-specific seed data.
"""

from __future__ import annotations

# https://wiki.leagueoflegends.com/en-us/Gold#Passive_gold_gain
SR_STARTING_GOLD = 500.0
SR_PASSIVE_GOLD_PER_10_SECONDS = 20.4
SR_PASSIVE_GOLD_START_SECONDS = 65.0

# https://wiki.leagueoflegends.com/en-us/Farming — first wave 0:35, then every 30s
SR_FIRST_WAVE_SPAWN_SECONDS = 35.0
SR_WAVE_INTERVAL_SECONDS = 30.0

# Experience to reach next level, levels 1→2 through 17→18 (17 values)
# https://wiki.leagueoflegends.com/en-us/Experience_(champion)
SR_XP_TO_NEXT_LEVEL: tuple[int, ...] = (
    280,
    380,
    480,
    580,
    680,
    740,
    800,
    880,
    920,
    980,
    1100,
    1180,
    1260,
    1340,
    1420,
    1480,
    1480,
)

# Jungle route abstraction (order-of-magnitude full clear; tune via calibration)
SR_JUNGLE_BASE_CYCLE_SECONDS = 90.0
SR_JUNGLE_BASE_ROUTE_GOLD = 85.0
SR_JUNGLE_BASE_ROUTE_XP = 400.0

# Pet treat thresholds for companion evolutions on Classic 5v5 (wiki Jungling § Jungle items).
# Not simulated in the farm loop; see ``LoLPerfmon.sim.jungle_items.SR_JUNGLE_COMPANION_EVOLVE_TREAT_THRESHOLDS``.


def default_minion_xp_by_level_tables() -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """
    XP per last-hit by minion type and champion level index 0..17.

    Offline fallback: smooth ramp between typical early (wiki order-of-magnitude) and
    late-lane values; not copied from a particular patch JSON.
    """
    melee = tuple(60.0 + 2.0 * i for i in range(18))
    caster = tuple(30.0 + 1.0 * i for i in range(18))
    siege = tuple(90.0 + 2.0 * i for i in range(18))
    return melee, caster, siege
