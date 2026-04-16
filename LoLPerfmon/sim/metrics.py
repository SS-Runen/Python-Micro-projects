from __future__ import annotations

from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.simulator import SimResult


def normalized_role_throughput(res: SimResult, mode: FarmMode, t_max: float) -> float:
    if t_max <= 0:
        return 0.0
    if mode == FarmMode.LANE:
        return res.total_lane_minions_cleared / (t_max / 60.0)
    return res.total_jungle_monsters_cleared / (t_max / 60.0)


def farm_gold_per_minute(res: SimResult, t_max: float) -> float:
    if t_max <= 0:
        return 0.0
    return res.total_farm_gold / (t_max / 60.0)


def composite_farm_score(
    res: SimResult,
    mode: FarmMode,
    t_max: float,
    w_throughput: float = 0.5,
    w_gold: float = 0.5,
) -> float:
    thr = normalized_role_throughput(res, mode, t_max)
    gpm = farm_gold_per_minute(res, t_max)
    return w_throughput * thr + w_gold * (gpm / 1000.0)
