"""
Optimal jungle companion sell timing: scan sell-at times at jungle cycle boundaries.

Uses :func:`default_build_optimizer_score` (``total_farm_gold``) with the same forward
sim as greedy farm (purchase hook) and optional ``jungle_sell_at_seconds`` on
:func:`simulate`.
"""

from __future__ import annotations

from .config import FarmMode
from .data_loader import GameDataBundle
from .greedy_farm_build import make_greedy_hook
from .simulator import PurchasePolicy, SimResult, default_build_optimizer_score, simulate


def optimal_jungle_sell_timing(
    data: GameDataBundle,
    champion_id: str,
    t_max: float,
    *,
    jungle_starter_item_id: str | None = None,
    jungle_sell_only_after_level_18: bool = False,
    eta_lane: float = 1.0,
    defer_purchases_until: float | None = None,
    epsilon: float = 1e-9,
    marginal_income_cap: bool = True,
) -> tuple[float | None, float, SimResult]:
    """
    Evaluate greedy jungle farm for each candidate sell time: never sell, then sell at
    ``base_cycle``, ``2*base_cycle``, ... up to ``t_max``. Returns
    ``(best_sell_at_seconds_or_None, best_score, best_SimResult)`` using
    :func:`default_build_optimizer_score`.
    """
    rules = data.rules
    dt = rules.jungle_base_cycle_seconds
    profile = data.champions[champion_id]
    items = data.items

    best_T: float | None = None
    best_score = float("-inf")
    best_res: SimResult | None = None

    candidates: list[float | None] = [None]
    t = dt
    while t <= t_max + 1e-9:
        candidates.append(t)
        t += dt

    for T in candidates:
        order: list[str] = []
        hook = make_greedy_hook(
            profile,
            items,
            defer_purchases_until,
            epsilon,
            order_sink=order,
            data=data,
            farm_mode=FarmMode.JUNGLE,
            eta_lane=eta_lane,
            marginal_income_cap=marginal_income_cap,
        )
        res = simulate(
            data,
            champion_id,
            FarmMode.JUNGLE,
            PurchasePolicy(buy_order=()),
            eta_lane=eta_lane,
            t_max=t_max,
            defer_purchases_until=defer_purchases_until,
            purchase_hook=hook,
            jungle_starter_item_id=jungle_starter_item_id,
            jungle_sell_at_seconds=T,
            jungle_sell_only_after_level_18=jungle_sell_only_after_level_18,
        )
        score = default_build_optimizer_score(res)
        if score > best_score + 1e-9:
            best_score = score
            best_res = res
            best_T = T

    assert best_res is not None
    return best_T, best_score, best_res


__all__ = ["optimal_jungle_sell_timing"]
