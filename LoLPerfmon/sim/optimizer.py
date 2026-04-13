from __future__ import annotations

import itertools
from typing import Callable

from .config import FarmMode
from .data_loader import GameDataBundle
from .simulator import (
    PurchasePolicy,
    SimResult,
    SimulationState,
    default_build_optimizer_score,
    default_clear_count_score,
    simulate,
)


def best_item_order_exhaustive(
    data: GameDataBundle,
    champion_id: str,
    farm_mode: FarmMode,
    item_ids: tuple[str, ...],
    score: Callable[[SimResult], float] = default_build_optimizer_score,
    eta_lane: float = 1.0,
    t_max: float | None = None,
    early_stop: Callable[[SimulationState], bool] | None = None,
    extrapolate_lane_waves: bool | None = None,
) -> tuple[tuple[str, ...], float, SimResult]:
    """
    Try every permutation of ``item_ids`` as fixed buy order; return best by ``score``.

    Default ``score`` is :func:`default_build_optimizer_score` (**total farm gold** from
    clears), not ``final_gold`` (wallet balance can reward underspending).

    To maximize **modeled minion or monster clears** (not gold-weighted lane income), pass e.g.
    ``score=lambda r: default_clear_count_score(r, farm_mode)`` — see :class:`~LoLPerfmon.sim.simulator.SimResult`
    fields ``total_lane_minions_cleared`` / ``total_jungle_monsters_cleared``.

    For **recipe-correct** goal lists, prefer :func:`LoLPerfmon.sim.build_path_optimizer.optimal_interleaved_build`
    or :func:`LoLPerfmon.sim.build_path_optimizer.acquisition_sequence_for_finished_roots`
    with **finished-item roots**; see ``DATA_SOURCES.md`` (Build optimization vs recipe expansion).

    Pass ``t_max=float("inf")`` with ``early_stop`` (e.g. :func:`LoLPerfmon.sim.greedy_farm_build.make_early_stop_six_build_endpoints`)
    to run until a stop condition; use ``extrapolate_lane_waves=True`` if the horizon can exceed
    the bundle’s precomputed wave list (see :func:`LoLPerfmon.sim.simulator.simulate`).
    """
    best_order: tuple[str, ...] = ()
    best_val = float("-inf")
    best_res: SimResult | None = None
    for perm in itertools.permutations(item_ids):
        pol = PurchasePolicy(buy_order=tuple(perm))
        res = simulate(
            data,
            champion_id,
            farm_mode,
            pol,
            eta_lane=eta_lane,
            t_max=t_max,
            early_stop=early_stop,
            extrapolate_lane_waves=extrapolate_lane_waves,
        )
        v = score(res)
        if v > best_val:
            best_val = v
            best_order = tuple(perm)
            best_res = res
    assert best_res is not None
    return best_order, best_val, best_res
