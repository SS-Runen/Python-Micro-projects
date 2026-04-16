from __future__ import annotations

from dataclasses import dataclass

from LoLPerfmon.sim.config import LANE_MINIONS_FIRST_SPAWN_SEC, JUNGLE_CAMPS_FIRST_SPAWN_SEC


@dataclass(frozen=True)
class LaneWaveSchedule:
    first_spawn_sec: float = LANE_MINIONS_FIRST_SPAWN_SEC
    interval_sec: float = 30.0
    minions_per_wave: float = 6.0


@dataclass(frozen=True)
class JungleCampSchedule:
    first_spawn_sec: float = JUNGLE_CAMPS_FIRST_SPAWN_SEC
    cycle_sec: float = 150.0
    monsters_per_cycle: float = 4.0


def lane_wave_index_at_time(t_sec: float, sched: LaneWaveSchedule) -> int:
    if t_sec < sched.first_spawn_sec:
        return -1
    return int((t_sec - sched.first_spawn_sec) // sched.interval_sec)


def next_lane_wave_time_after(t_sec: float, sched: LaneWaveSchedule) -> float:
    if t_sec < sched.first_spawn_sec:
        return sched.first_spawn_sec
    idx = lane_wave_index_at_time(t_sec, sched)
    return sched.first_spawn_sec + (idx + 1) * sched.interval_sec
