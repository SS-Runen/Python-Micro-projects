from __future__ import annotations

import itertools
from typing import Callable

from .config import FarmMode
from .data_loader import GameDataBundle
from .simulator import PurchasePolicy, SimResult, default_build_optimizer_score, simulate


def best_item_order_exhaustive(
    data: GameDataBundle,
    champion_id: str,
    farm_mode: FarmMode,
    item_ids: tuple[str, ...],
    score: Callable[[SimResult], float] = default_build_optimizer_score,
    eta_lane: float = 1.0,
    t_max: float | None = None,
) -> tuple[tuple[str, ...], float, SimResult]:
    """
    Try every permutation of ``item_ids`` as fixed buy order; return best by ``score``.

    Default ``score`` is :func:`default_build_optimizer_score` (**total farm gold** from
    clears), not ``final_gold`` (wallet balance can reward underspending).

    For **recipe-correct** goal lists, prefer :func:`LoLPerfmon.sim.build_path_optimizer.optimal_interleaved_build`
    or :func:`LoLPerfmon.sim.build_path_optimizer.acquisition_sequence_for_finished_roots`
    with **finished-item roots**; see ``DATA_SOURCES.md`` (Build optimization vs recipe expansion).
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
        )
        v = score(res)
        if v > best_val:
            best_val = v
            best_order = tuple(perm)
            best_res = res
    assert best_res is not None
    return best_order, best_val, best_res
