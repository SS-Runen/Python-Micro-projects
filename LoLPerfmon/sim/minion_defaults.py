"""
Default minion gold / HP vs game minute using linear interpolation between anchors.

Anchors sit within typical Summoner's Rift ranges (wiki / design order-of-magnitude),
not copied from a specific patch file.
"""

from __future__ import annotations

from typing import Any


def default_minion_economy_tables() -> dict[str, Any]:
    """
    Two-point interpolation per type: minute 0 and minute 25 (mid-game proxy).
    Values scale linearly between; extrapolation clamps to endpoints.
    Extrapolated lane waves (see :mod:`LoLPerfmon.sim.wave_schedule`) use the same tables by game minute.
    """
    return {
        "melee": {
            "gold_per_kill": {"0": 21.0, "25": 27.0},
            "hp": {"0": 480.0, "25": 680.0},
        },
        "caster": {
            "gold_per_kill": {"0": 14.0, "25": 19.0},
            "hp": {"0": 280.0, "25": 360.0},
        },
        "siege": {
            "gold_per_kill": {"0": 60.0, "25": 70.0},
            "hp": {"0": 900.0, "25": 1150.0},
        },
    }
