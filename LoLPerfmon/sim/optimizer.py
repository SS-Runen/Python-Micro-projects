from __future__ import annotations

import itertools
from typing import Callable

from .config import FarmMode
from .data_loader import GameDataBundle
from .simulator import PurchasePolicy, SimResult, simulate


def best_item_order_exhaustive(
    data: GameDataBundle,
    champion_id: str,
    farm_mode: FarmMode,
    item_ids: tuple[str, ...],
    score: Callable[[SimResult], float] = lambda r: r.final_gold,
    eta_lane: float = 1.0,
    t_max: float | None = None,
) -> tuple[tuple[str, ...], float, SimResult]:
    """
    Try every permutation of ``item_ids`` as fixed buy order; return best by ``score``.
    Practical only for small lists (n! simulations).
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
