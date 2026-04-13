"""
Greedy and bounded-beam farm build search (lane or jungle). See OPTIMIZATION_CRITERIA.md.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable, Literal

from .clear import effective_dps
from .config import FarmMode
from .data_loader import GameDataBundle
from .marginal_farm_tick import marginal_farm_gold_per_tick_derivative
from .models import ChampionProfile, ItemDef, is_build_endpoint_item
from .simulator import (
    MAX_INVENTORY_SLOTS,
    PurchasePolicy,
    SimResult,
    SimulationState,
    acquire_goal,
    inventory_count,
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
        blocked_purchase_ids=set(s.blocked_purchase_ids),
    )


def _marginal_candidates(
    state: SimulationState,
    profile: ChampionProfile,
    items: dict,
    epsilon: float,
    *,
    data: GameDataBundle | None = None,
    farm_mode: FarmMode = FarmMode.LANE,
    eta_lane: float = 1.0,
    marginal_income_cap: bool = True,
) -> list[tuple[str, float, float, float]]:
    """
    One pass over ``items``: acquisitions that succeed on a snapshot and pass marginal rules.
    Returns tuples ``(item_id, score, delta_dps, gold_paid)`` unsorted.

    With ``marginal_income_cap`` and ``data`` set, score uses a first-order farm tick estimate
    ``(d tick_gold / d dps) * Δdps / gold_paid`` (SciPy ``approx_fprime`` on capped throughput);
    candidates with negligible marginal farm gold per tick are dropped even if Δdps > 0.
    """
    base_stats = total_stats(profile, state.level, tuple(state.inventory), items)
    dps0 = effective_dps(profile, state.level, base_stats)
    dg_ddps = 0.0
    if marginal_income_cap and data is not None:
        dg_ddps = marginal_farm_gold_per_tick_derivative(data, farm_mode, eta_lane, profile, state)
    out: list[tuple[str, float, float, float]] = []
    for iid in sorted(items.keys()):
        if iid in state.blocked_purchase_ids:
            continue
        it_def = items[iid]
        if inventory_count(state.inventory, iid) >= it_def.max_inventory_copies:
            continue
        trial = _snapshot_state(state)
        spent_before = trial.total_gold_spent_on_items
        if not acquire_goal(trial, iid, items):
            continue
        paid = trial.total_gold_spent_on_items - spent_before
        st1 = total_stats(profile, trial.level, tuple(trial.inventory), items)
        dps1 = effective_dps(profile, trial.level, st1)
        delta = dps1 - dps0
        if delta <= 1e-15:
            continue
        denom = max(paid, epsilon)
        if marginal_income_cap and data is not None:
            marginal_farm = dg_ddps * delta
            if marginal_farm <= 1e-18:
                continue
            score = marginal_farm / denom
        else:
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
    *,
    data: GameDataBundle | None = None,
    farm_mode: FarmMode = FarmMode.LANE,
    eta_lane: float = 1.0,
    marginal_income_cap: bool = True,
) -> list[tuple[str, float, float, float]]:
    """Sorted best-first: score desc, delta desc, item_id asc."""
    cands = _marginal_candidates(
        state,
        profile,
        items,
        epsilon,
        data=data,
        farm_mode=farm_mode,
        eta_lane=eta_lane,
        marginal_income_cap=marginal_income_cap,
    )
    cands.sort(key=lambda t: (-t[1], -t[2], t[0]))
    return cands


def _greedy_purchase_burst(
    state: SimulationState,
    profile: ChampionProfile,
    items: dict,
    defer_purchases_until: float | None,
    epsilon: float,
    order_sink: list[str] | None = None,
    *,
    data: GameDataBundle | None = None,
    farm_mode: FarmMode = FarmMode.LANE,
    eta_lane: float = 1.0,
    marginal_income_cap: bool = True,
) -> None:
    if defer_purchases_until is not None and state.time_seconds + 1e-9 < defer_purchases_until:
        return
    while True:
        cands = _marginal_candidates(
            state,
            profile,
            items,
            epsilon,
            data=data,
            farm_mode=farm_mode,
            eta_lane=eta_lane,
            marginal_income_cap=marginal_income_cap,
        )
        best = _pick_best_marginal(cands)
        if best is None:
            break
        if not acquire_goal(state, best, items):
            break
        if order_sink is not None:
            order_sink.append(best)


def make_early_stop_full_inventory_no_dps_marginal(
    profile: ChampionProfile,
    items: dict,
    epsilon: float,
    *,
    data: GameDataBundle,
    farm_mode: FarmMode = FarmMode.LANE,
    eta_lane: float = 1.0,
) -> Callable[[SimulationState], bool]:
    """
    End simulation when the bag has :data:`MAX_INVENTORY_SLOTS` items and
    :func:`_marginal_candidates` finds no acquisition that increases modeled
    :func:`~LoLPerfmon.sim.clear.effective_dps` (``marginal_income_cap=False``).
    """

    def early_stop(state: SimulationState) -> bool:
        if len(state.inventory) < MAX_INVENTORY_SLOTS:
            return False
        cands = _marginal_candidates(
            state,
            profile,
            items,
            epsilon,
            data=data,
            farm_mode=farm_mode,
            eta_lane=eta_lane,
            marginal_income_cap=False,
        )
        return len(cands) == 0

    return early_stop


def make_early_stop_six_build_endpoints(
    items: dict[str, ItemDef],
) -> Callable[[SimulationState], bool]:
    """
    End when the bag has :data:`MAX_INVENTORY_SLOTS` items and each is a **build endpoint**
    (Data Dragon ``into`` empty — see :func:`~LoLPerfmon.sim.models.is_build_endpoint_item`).
    Missing item ids are treated as non-endpoints.
    """

    def early_stop(state: SimulationState) -> bool:
        if len(state.inventory) < MAX_INVENTORY_SLOTS:
            return False
        for iid in state.inventory:
            it = items.get(iid)
            if it is None or not is_build_endpoint_item(it):
                return False
        return True

    return early_stop


def make_greedy_hook(
    profile: ChampionProfile,
    items: dict,
    defer_purchases_until: float | None,
    epsilon: float,
    order_sink: list[str] | None = None,
    *,
    data: GameDataBundle | None = None,
    farm_mode: FarmMode = FarmMode.LANE,
    eta_lane: float = 1.0,
    marginal_income_cap: bool = True,
) -> Callable[[SimulationState], None]:
    def purchase_hook(state: SimulationState) -> None:
        _greedy_purchase_burst(
            state,
            profile,
            items,
            defer_purchases_until,
            epsilon,
            order_sink,
            data=data,
            farm_mode=farm_mode,
            eta_lane=eta_lane,
            marginal_income_cap=marginal_income_cap,
        )

    return purchase_hook


make_greedy_lane_hook = make_greedy_hook


def make_forced_prefix_then_greedy_hook(
    profile: ChampionProfile,
    items: dict,
    defer_purchases_until: float | None,
    epsilon: float,
    forced_prefix: tuple[str, ...],
    order_sink: list[str] | None = None,
    *,
    data: GameDataBundle | None = None,
    farm_mode: FarmMode = FarmMode.LANE,
    eta_lane: float = 1.0,
    marginal_income_cap: bool = True,
) -> Callable[[SimulationState], None]:
    forced: deque[str] = deque(forced_prefix)

    def purchase_hook(state: SimulationState) -> None:
        if defer_purchases_until is not None and state.time_seconds + 1e-9 < defer_purchases_until:
            return
        while forced:
            fid = forced[0]
            if fid in state.blocked_purchase_ids:
                forced.popleft()
                continue
            itd = items.get(fid)
            if itd is not None and inventory_count(state.inventory, fid) >= itd.max_inventory_copies:
                forced.popleft()
                continue
            if acquire_goal(state, fid, items):
                forced.popleft()
                if order_sink is not None:
                    order_sink.append(fid)
            else:
                return
        _greedy_purchase_burst(
            state,
            profile,
            items,
            defer_purchases_until,
            epsilon,
            order_sink,
            data=data,
            farm_mode=farm_mode,
            eta_lane=eta_lane,
            marginal_income_cap=marginal_income_cap,
        )

    return purchase_hook


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
    farm_mode: FarmMode = FarmMode.LANE,
    jungle_starter_item_id: str | None = None,
    marginal_income_cap: bool = True,
) -> tuple[tuple[str, ...], float, SimResult, GreedyFarmMetadata]:
    """
    Greedily maximize marginal farm income proxy (or Δeffective_dps / gold when cap off) at each
    purchase opportunity. Primary score for comparison is ``total_farm_gold`` on the returned
    :class:`SimResult`. ``farm_mode``: lane (minion waves) or jungle (camp cycles)—mutually
    exclusive per run.
    """
    order: list[str] = []
    hook = make_greedy_hook(
        data.champions[champion_id],
        data.items,
        defer_purchases_until,
        epsilon,
        order_sink=order,
        data=data,
        farm_mode=farm_mode,
        eta_lane=eta_lane,
        marginal_income_cap=marginal_income_cap,
    )
    res = simulate(
        data,
        champion_id,
        farm_mode,
        PurchasePolicy(buy_order=()),
        eta_lane=eta_lane,
        t_max=t_max,
        defer_purchases_until=defer_purchases_until,
        purchase_hook=hook,
        jungle_starter_item_id=jungle_starter_item_id,
    )
    meta = GreedyFarmMetadata(epsilon=epsilon, purchase_count=len(order))
    return tuple(order), res.total_farm_gold, res, meta


def greedy_farm_build_waveclear_dps_saturation(
    data: GameDataBundle,
    champion_id: str,
    *,
    eta_lane: float = 1.0,
    t_max: float | None = None,
    defer_purchases_until: float | None = None,
    epsilon: float = 1e-9,
    farm_mode: FarmMode = FarmMode.LANE,
    jungle_starter_item_id: str | None = None,
) -> tuple[tuple[str, ...], SimResult, GreedyFarmMetadata, bool]:
    """
    Greedy shop using **Δeffective_dps / gold** only (no throughput-capped marginal farm tick).
    Stops early when inventory is full (:data:`MAX_INVENTORY_SLOTS`) and no modeled purchase
    raises :func:`~LoLPerfmon.sim.clear.effective_dps`; otherwise runs until ``t_max`` or wave data
    ends. The fourth return is True iff :attr:`SimResult.ended_by_early_stop`.
    """
    profile = data.champions[champion_id]
    order: list[str] = []
    early = make_early_stop_full_inventory_no_dps_marginal(
        profile,
        data.items,
        epsilon,
        data=data,
        farm_mode=farm_mode,
        eta_lane=eta_lane,
    )
    hook = make_greedy_hook(
        profile,
        data.items,
        defer_purchases_until,
        epsilon,
        order_sink=order,
        data=data,
        farm_mode=farm_mode,
        eta_lane=eta_lane,
        marginal_income_cap=False,
    )
    res = simulate(
        data,
        champion_id,
        farm_mode,
        PurchasePolicy(buy_order=()),
        eta_lane=eta_lane,
        t_max=t_max,
        defer_purchases_until=defer_purchases_until,
        purchase_hook=hook,
        jungle_starter_item_id=jungle_starter_item_id,
        early_stop=early,
    )
    meta = GreedyFarmMetadata(epsilon=epsilon, purchase_count=len(order))
    return tuple(order), res, meta, res.ended_by_early_stop


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
    farm_mode: FarmMode = FarmMode.LANE,
    marginal_objective: Literal["dps_per_gold", "horizon_greedy_roi"] = "dps_per_gold",
    horizon_candidate_cap: int = 48,
    jungle_starter_item_id: str | None = None,
    marginal_income_cap: bool = True,
    leaf_score: Literal["total_farm_gold", "early_dps_auc", "farm_gold_per_gold_spent"] = "total_farm_gold",
    early_horizon_seconds: float = 900.0,
) -> tuple[tuple[str, ...], float, SimResult, BeamFarmMetadata | GreedyFarmMetadata]:
    """
    Beam search over purchase prefixes (depth ``beam_depth``, width ``beam_width``).
    Default leaf score is full-horizon ``total_farm_gold``; use ``leaf_score='early_dps_auc'``
    to maximize ∫ modeled effective DPS dt over ``early_horizon_seconds``. Greedy tail after prefix.
    """
    from .farm_build_search import FarmBuildSearch

    search = FarmBuildSearch(
        data=data,
        champion_id=champion_id,
        farm_mode=farm_mode,
        eta_lane=eta_lane,
        t_max=t_max,
        defer_purchases_until=defer_purchases_until,
        epsilon=epsilon,
        beam_depth=beam_depth,
        beam_width=beam_width,
        max_leaf_evals=max_leaf_evals,
        marginal_objective=marginal_objective,
        horizon_candidate_cap=horizon_candidate_cap,
        jungle_starter_item_id=jungle_starter_item_id,
        marginal_income_cap=marginal_income_cap,
        leaf_score=leaf_score,
        early_horizon_seconds=early_horizon_seconds,
    )
    return search.run()


__all__ = [
    "BeamFarmMetadata",
    "GreedyFarmMetadata",
    "beam_refined_farm_build",
    "greedy_farm_build",
    "greedy_farm_build_waveclear_dps_saturation",
    "make_early_stop_full_inventory_no_dps_marginal",
    "make_early_stop_six_build_endpoints",
    "make_forced_prefix_then_greedy_hook",
    "make_greedy_hook",
    "make_greedy_lane_hook",
    "ranked_marginal_acquisitions",
]
