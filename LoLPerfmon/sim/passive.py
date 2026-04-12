from __future__ import annotations

from .config import GameConfig


def passive_accumulated(t_seconds: float, config: GameConfig | None = None) -> float:
    """
    Total passive gold accrued from game start (t=0) through t_seconds.
    SR: 20.4 gold / 10s starting at 1:05 (65s). Equivalent to continuous linear rate
    after start; the client accrues every 0.5s but the time integral matches this.
    """
    cfg = config or GameConfig()
    if t_seconds <= cfg.passive_gold_start_seconds:
        return 0.0
    return (t_seconds - cfg.passive_gold_start_seconds) * cfg.passive_rate_per_second()


def passive_gold_in_interval(
    t0_seconds: float, t1_seconds: float, config: GameConfig | None = None
) -> float:
    """Passive gold gained in [t0, t1] with t0 <= t1."""
    return passive_accumulated(t1_seconds, config) - passive_accumulated(t0_seconds, config)


def passive_accumulated_discrete_half_second_steps(
    t_seconds: float, config: GameConfig | None = None
) -> float:
    """
    Reference oracle: sum accrual each 0.5s tick after passive start (wiki behavior).
    Each tick grants rate * 0.5 = (per10/10) * 0.5 gold.
    """
    cfg = config or GameConfig()
    if t_seconds <= cfg.passive_gold_start_seconds:
        return 0.0
    rate = cfg.passive_rate_per_second()
    tick = 0.5
    total = 0.0
    t = cfg.passive_gold_start_seconds
    while t + tick <= t_seconds + 1e-12:
        total += rate * tick
        t += tick
    remainder = t_seconds - t
    if remainder > 1e-12:
        total += rate * remainder
    return total
