"""
Marginal farm gold per discrete tick vs effective DPS (capped lane/jungle throughput).

Uses :func:`scipy.optimize.approx_fprime` on scalar maps ``dps -> tick_gold`` that mirror
:class:`~LoLPerfmon.sim.simulator.simulate` lane/jungle formulas. :class:`pandas.Series`
holds step metadata for the finite-difference step size.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import approx_fprime

from .clear import effective_dps, lane_available_seconds, wave_gold_if_full_clear, wave_hp_budget
from .config import FarmMode
from .data_loader import GameDataBundle, GameRules, WaveComposition, wave_minion_count
from .models import ChampionProfile
from .simulator import SimulationState
from .stats import total_stats


def _max_wave_index(data: GameDataBundle) -> int:
    if not data.waves:
        return 0
    return max(w.wave_index for w in data.waves)


def lane_wave_and_game_minute(data: GameDataBundle, time_seconds: float) -> tuple[WaveComposition | None, float]:
    """Wave composition and game minute (same convention as :func:`~LoLPerfmon.sim.simulator.simulate` lane loop)."""
    rules = data.rules
    max_k = _max_wave_index(data)
    dt = time_seconds - rules.first_wave_spawn_seconds
    if dt < -1e-9:
        k = 0
    else:
        k = int(round(dt / rules.wave_interval_seconds))
    k = max(0, min(k, max_k))
    wave = data.wave_at_index(k)
    if wave is None:
        return None, 0.0
    t_wave = rules.first_wave_spawn_seconds + k * rules.wave_interval_seconds
    return wave, t_wave / 60.0


def _lane_tick_gold_array(
    dps_vec: np.ndarray,
    wave: WaveComposition,
    game_minute: float,
    data: GameDataBundle,
    eta_lane: float,
) -> np.ndarray:
    rules = data.rules
    lane_win = lane_available_seconds(
        rules.wave_interval_seconds,
        rules.lane_engagement_overhead_seconds,
    )
    hp = wave_hp_budget(wave, game_minute, data)
    dps = np.maximum(dps_vec, 1e-9)
    ct = hp / dps
    thr = np.minimum(1.0, lane_win / np.maximum(ct, 1e-9)) * eta_lane
    gold_full = wave_gold_if_full_clear(wave, game_minute, data)
    return (gold_full * thr).astype(np.float64, copy=False)


def _lane_tick_minions_array(
    dps_vec: np.ndarray,
    wave: WaveComposition,
    game_minute: float,
    data: GameDataBundle,
    eta_lane: float,
) -> np.ndarray:
    rules = data.rules
    lane_win = lane_available_seconds(
        rules.wave_interval_seconds,
        rules.lane_engagement_overhead_seconds,
    )
    hp = wave_hp_budget(wave, game_minute, data)
    dps = np.maximum(dps_vec, 1e-9)
    ct = hp / dps
    thr = np.minimum(1.0, lane_win / np.maximum(ct, 1e-9)) * eta_lane
    nm = float(wave_minion_count(wave))
    return (thr * nm).astype(np.float64, copy=False)


def lane_tick_gold_derivative_wrt_dps(
    dps0: float,
    wave: WaveComposition,
    game_minute: float,
    data: GameDataBundle,
    eta_lane: float,
) -> float:
    """``d(tick_gold)/d(dps)`` at ``dps0`` via SciPy finite differences on the lane tick map."""

    def tick_vec(x: np.ndarray) -> np.ndarray:
        return _lane_tick_gold_array(x, wave, game_minute, data, eta_lane)

    meta = pd.Series(
        {
            "dps": float(dps0),
            "eps_scale": max(1.0, abs(float(dps0))),
            "mode": "lane",
        }
    )
    x0 = np.asarray([dps0], dtype=np.float64)
    eps = float(np.sqrt(np.finfo(float).eps) * meta["eps_scale"])
    jac = approx_fprime(x0, tick_vec, epsilon=eps)
    return float(jac[0])


def lane_tick_minions_cleared_derivative_wrt_dps(
    dps0: float,
    wave: WaveComposition,
    game_minute: float,
    data: GameDataBundle,
    eta_lane: float,
) -> float:
    """``d(thr * minion_count)/d(dps)`` for the lane tick (uniform minion count)."""

    def tick_vec(x: np.ndarray) -> np.ndarray:
        return _lane_tick_minions_array(x, wave, game_minute, data, eta_lane)

    meta = pd.Series(
        {
            "dps": float(dps0),
            "eps_scale": max(1.0, abs(float(dps0))),
            "mode": "lane_minions",
        }
    )
    x0 = np.asarray([dps0], dtype=np.float64)
    eps = float(np.sqrt(np.finfo(float).eps) * meta["eps_scale"])
    jac = approx_fprime(x0, tick_vec, epsilon=eps)
    return float(jac[0])


def jungle_route_tick_gold_from_dps(dps: float, rules: GameRules) -> float:
    """One jungle cycle gold tick; matches ``simulate`` jungle branch (``eff`` cap)."""
    return float(jungle_route_tick_gold_vec(np.array([dps], dtype=np.float64), rules)[0])


def jungle_route_tick_gold_vec(dps_vec: np.ndarray, rules: GameRules) -> np.ndarray:
    dps = np.maximum(dps_vec, 1e-9)
    cycle = rules.jungle_base_cycle_seconds * 80.0 / dps + max(
        0.0, rules.jungle_engagement_overhead_seconds
    )
    eff = np.minimum(1.0, rules.jungle_base_cycle_seconds / np.maximum(cycle, 1e-9))
    return (rules.jungle_base_route_gold * eff).astype(np.float64, copy=False)


def jungle_route_tick_monsters_vec(dps_vec: np.ndarray, rules: GameRules) -> np.ndarray:
    dps = np.maximum(dps_vec, 1e-9)
    cycle = rules.jungle_base_cycle_seconds * 80.0 / dps + max(
        0.0, rules.jungle_engagement_overhead_seconds
    )
    eff = np.minimum(1.0, rules.jungle_base_cycle_seconds / np.maximum(cycle, 1e-9))
    return (eff * float(rules.jungle_monsters_per_route)).astype(np.float64, copy=False)


def jungle_tick_gold_derivative_wrt_dps(dps0: float, rules: GameRules) -> float:
    def tick_vec(x: np.ndarray) -> np.ndarray:
        return jungle_route_tick_gold_vec(x, rules)

    meta = pd.Series({"dps": float(dps0), "eps_scale": max(1.0, abs(float(dps0))), "mode": "jungle"})
    x0 = np.asarray([dps0], dtype=np.float64)
    eps = float(np.sqrt(np.finfo(float).eps) * meta["eps_scale"])
    jac = approx_fprime(x0, tick_vec, epsilon=eps)
    return float(jac[0])


def jungle_tick_monsters_cleared_derivative_wrt_dps(dps0: float, rules: GameRules) -> float:
    def tick_vec(x: np.ndarray) -> np.ndarray:
        return jungle_route_tick_monsters_vec(x, rules)

    meta = pd.Series({"dps": float(dps0), "eps_scale": max(1.0, abs(float(dps0))), "mode": "jungle_monsters"})
    x0 = np.asarray([dps0], dtype=np.float64)
    eps = float(np.sqrt(np.finfo(float).eps) * meta["eps_scale"])
    jac = approx_fprime(x0, tick_vec, epsilon=eps)
    return float(jac[0])


def marginal_farm_gold_per_tick_derivative(
    data: GameDataBundle,
    farm_mode: FarmMode,
    eta_lane: float,
    profile: ChampionProfile,
    state: SimulationState,
) -> float:
    """
    Derivative of the **next** farm gold tick w.r.t. ``effective_dps``, holding level/inventory
    fixed except as reflected in the current ``dps0`` snapshot (same local linearization target
    as greedy marginal items).
    """
    base_stats = total_stats(profile, state.level, tuple(state.inventory), data.items)
    dps0 = float(max(effective_dps(profile, state.level, base_stats), 1e-9))

    if farm_mode == FarmMode.LANE:
        wave, gm = lane_wave_and_game_minute(data, state.time_seconds)
        if wave is None:
            return 0.0
        return lane_tick_gold_derivative_wrt_dps(dps0, wave, gm, data, eta_lane)
    return jungle_tick_gold_derivative_wrt_dps(dps0, data.rules)


def marginal_clear_units_per_tick_derivative(
    data: GameDataBundle,
    farm_mode: FarmMode,
    eta_lane: float,
    profile: ChampionProfile,
    state: SimulationState,
) -> float:
    """Derivative of the next lane minion or jungle monster tick w.r.t. ``effective_dps`` (clear-volume objective)."""
    base_stats = total_stats(profile, state.level, tuple(state.inventory), data.items)
    dps0 = float(max(effective_dps(profile, state.level, base_stats), 1e-9))

    if farm_mode == FarmMode.LANE:
        wave, gm = lane_wave_and_game_minute(data, state.time_seconds)
        if wave is None:
            return 0.0
        return lane_tick_minions_cleared_derivative_wrt_dps(dps0, wave, gm, data, eta_lane)
    return jungle_tick_monsters_cleared_derivative_wrt_dps(dps0, data.rules)


__all__ = [
    "jungle_route_tick_gold_from_dps",
    "jungle_route_tick_gold_vec",
    "jungle_tick_gold_derivative_wrt_dps",
    "lane_tick_gold_derivative_wrt_dps",
    "lane_wave_and_game_minute",
    "lane_tick_minions_cleared_derivative_wrt_dps",
    "jungle_route_tick_monsters_vec",
    "jungle_tick_monsters_cleared_derivative_wrt_dps",
    "marginal_farm_gold_per_tick_derivative",
    "marginal_clear_units_per_tick_derivative",
]
