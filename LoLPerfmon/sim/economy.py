from __future__ import annotations

from LoLPerfmon.sim.config import PASSIVE_GOLD_PER_SEC, STARTING_GOLD


def passive_gold_over_interval(dt_sec: float) -> float:
    return PASSIVE_GOLD_PER_SEC * max(0.0, dt_sec)


def starting_wallet() -> float:
    return STARTING_GOLD
