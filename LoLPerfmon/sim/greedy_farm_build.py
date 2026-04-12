"""
Greedy and bounded-beam farm build search (lane). See OPTIMIZATION_CRITERIA.md.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable

from .clear import effective_dps
from .config import FarmMode
from .data_loader import GameDataBundle
from .models import ChampionProfile
from .simulator import (
    PurchasePolicy,
    SimResult,
    SimulationState,
    acquire_goal,
    simulate,
)
from .stats import total_stats


def _snapshot_state(s: SimulationState) -> SimulationState:
    return SimulationState(
        time_seconds=s.time_seconds,
        gold=s.gold,
        inventory=list(s.inventory),
        total_xp=s.total_xp,
        level=s.level,
        buy_queue=list(s.buy_queue),
        total_gold_spent_on_items=s.total_gold_spent_on_items,
    )


def _marginal_candidates(
    state: SimulationState,
    profile: ChampionProfile,
    items: dict,
    epsilon: float,
) -> list[tuple[str, float, float, float]]:
    """
    One pass over ``items``: acquisitions that succeed on a snapshot and have positive
    Δeffective_dps. Returns tuples ``(item_id, score, delta_dps, gold_paid)`` unsorted.
    """
    base_stats = total_stats(profile, state.level, tuple(state.inventory), items)
    dps0 = effective_dps(profile, base_stats)
    out: list[tuple[str, float, float, float]] = []
    for iid in sorted(items.keys()):
        trial = _snapshot_state(state)
        spent_before = trial.total_gold_spent_on_items
        if not acquire_goal(trial, iid, items):
            continue
        paid = trial.total_gold_spent_on_items - spent_before
        st1 = total_stats(profile, trial.level, tuple(trial.inventory), items)
        dps1 = effective_dps(profile, st1)
        delta = dps1 - dps0
        if delta <= 1e-15:
            continue
        denom = max(paid, epsilon)
        score = delta / denom
        out.append((iid, score, delta, paid))
    return out


def _pick_best_marginal(
    candidates: list[tuple[str, float, float, float]],
) -> str | None:
    """Deterministic: max score, then max delta, then min item_id."""
    if not candidates:
        return None
    candidates.sort(key=lambda t: (-t[1], -t[2], t[0]))
    return candidates[0][0]


def ranked_marginal_acquisitions(
    state: SimulationState,
    profile: ChampionProfile,
    items: dict,
    epsilon: float,
) -> list[tuple[str, float, float, float]]:
    """Sorted best-first: score desc, delta desc, item_id asc."""
    cands = _marginal_candidates(state, profile, items, epsilon)
    cands.sort(key=lambda t: (-t[1], -t[2], t[0]))
    return cands


def _greedy_purchase_burst(
    state: SimulationState,
    profile: ChampionProfile,
    items: dict,
    defer_purchases_until: float | None,
    epsilon: float,
    order_sink: list[str] | None = None,
) -> None:
    if defer_purchases_until is not None and state.time_seconds + 1e-9 < defer_purchases_until:
        return
    while True:
        cands = _marginal_candidates(state, profile, items, epsilon)
        best = _pick_best_marginal(cands)
        if best is None:
            break
        if not acquire_goal(state, best, items):
            break
        if order_sink is not None:
            order_sink.append(best)


def make_greedy_lane_hook(
    profile: ChampionProfile,
    items: dict,
    defer_purchases_until: float | None,
    epsilon: float,
    order_sink: list[str] | None = None,
) -> Callable[[SimulationState], None]:
    def lane_hook(state: SimulationState) -> None:
        _greedy_purchase_burst(state, profile, items, defer_purchases_until, epsilon, order_sink)

    return lane_hook


def make_forced_prefix_then_greedy_hook(
    profile: ChampionProfile,
    items: dict,
    defer_purchases_until: float | None,
    epsilon: float,
    forced_prefix: tuple[str, ...],
    order_sink: list[str] | None = None,
) -> Callable[[SimulationState], None]:
    forced: deque[str] = deque(forced_prefix)

    def lane_hook(state: SimulationState) -> None:
        if defer_purchases_until is not None and state.time_seconds + 1e-9 < defer_purchases_until:
            return
        while forced:
            fid = forced[0]
            if acquire_goal(state, fid, items):
                forced.popleft()
                if order_sink is not None:
                    order_sink.append(fid)
            else:
                return
        _greedy_purchase_burst(state, profile, items, defer_purchases_until, epsilon, order_sink)

    return lane_hook


@dataclass(frozen=True)
class GreedyFarmMetadata:
    epsilon: float
    purchase_count: int


@dataclass(frozen=True)
class BeamFarmMetadata:
    beam_depth: int
    beam_width: int
    max_leaf_evals: int
    epsilon: float
    leaves_evaluated: int


def greedy_farm_build(
    data: GameDataBundle,
    champion_id: str,
    eta_lane: float = 1.0,
    t_max: float | None = None,
    defer_purchases_until: float | None = None,
    epsilon: float = 1e-9,
) -> tuple[tuple[str, ...], float, SimResult, GreedyFarmMetadata]:
    """
    Lane-only: greedily maximize Δeffective_dps / gold at each purchase opportunity.
    Primary score for comparison is ``total_farm_gold`` on the returned :class:`SimResult`.
    """
    order: list[str] = []
    hook = make_greedy_lane_hook(
        data.champions[champion_id],
        data.items,
        defer_purchases_until,
        epsilon,
        order_sink=order,
    )
    res = simulate(
        data,
        champion_id,
        FarmMode.LANE,
        PurchasePolicy(buy_order=()),
        eta_lane=eta_lane,
        t_max=t_max,
        defer_purchases_until=defer_purchases_until,
        lane_purchase_hook=hook,
    )
    meta = GreedyFarmMetadata(epsilon=epsilon, purchase_count=len(order))
    return tuple(order), res.total_farm_gold, res, meta


def beam_refined_farm_build(
    data: GameDataBundle,
    champion_id: str,
    eta_lane: float = 1.0,
    t_max: float | None = None,
    defer_purchases_until: float | None = None,
    epsilon: float = 1e-9,
    beam_depth: int = 1,
    beam_width: int = 3,
    max_leaf_evals: int = 27,
) -> tuple[tuple[str, ...], float, SimResult, BeamFarmMetadata | GreedyFarmMetadata]:
    """
    Compares greedy to up to ``beam_width`` first purchases from ranked marginals at t=0
    (beam depth 1 only; ``beam_depth`` > 1 is clamped to 1).

    Each leaf is a full simulation with forced first purchase then greedy tail.
    """
    profile = data.champions[champion_id]
    if beam_depth > 1:
        beam_depth = 1
    initial = SimulationState(
        time_seconds=0.0,
        gold=float(data.rules.start_gold),
        inventory=[],
        total_xp=0.0,
        level=1,
        buy_queue=[],
        total_gold_spent_on_items=0.0,
    )
    ranked = ranked_marginal_acquisitions(initial, profile, data.items, epsilon)
    if not ranked:
        return greedy_farm_build(data, champion_id, eta_lane, t_max, defer_purchases_until, epsilon)

    candidates = [r[0] for r in ranked[:beam_width]]
    leaves_evaluated = 0
    best_res: SimResult | None = None
    best_order: tuple[str, ...] = ()
    best_val = float("-inf")

    order_g: list[str] = []
    hook_g = make_greedy_lane_hook(
        profile, data.items, defer_purchases_until, epsilon, order_sink=order_g
    )
    res_g = simulate(
        data,
        champion_id,
        FarmMode.LANE,
        PurchasePolicy(buy_order=()),
        eta_lane=eta_lane,
        t_max=t_max,
        defer_purchases_until=defer_purchases_until,
        lane_purchase_hook=hook_g,
    )
    leaves_evaluated += 1
    best_val = res_g.total_farm_gold
    best_res = res_g
    best_order = tuple(order_g)

    for first in candidates:
        if leaves_evaluated >= max_leaf_evals:
            break
        order_i: list[str] = []
        hook_f = make_forced_prefix_then_greedy_hook(
            profile, data.items, defer_purchases_until, epsilon, (first,), order_sink=order_i
        )
        res_i = simulate(
            data,
            champion_id,
            FarmMode.LANE,
            PurchasePolicy(buy_order=()),
            eta_lane=eta_lane,
            t_max=t_max,
            defer_purchases_until=defer_purchases_until,
            lane_purchase_hook=hook_f,
        )
        leaves_evaluated += 1
        if res_i.total_farm_gold > best_val + 1e-9:
            best_val = res_i.total_farm_gold
            best_res = res_i
            best_order = tuple(order_i)

    assert best_res is not None
    meta = BeamFarmMetadata(
        beam_depth=beam_depth,
        beam_width=beam_width,
        max_leaf_evals=max_leaf_evals,
        epsilon=epsilon,
        leaves_evaluated=leaves_evaluated,
    )
    return best_order, best_val, best_res, meta


__all__ = [
    "BeamFarmMetadata",
    "GreedyFarmMetadata",
    "beam_refined_farm_build",
    "greedy_farm_build",
    "make_forced_prefix_then_greedy_hook",
    "make_greedy_lane_hook",
    "ranked_marginal_acquisitions",
]
