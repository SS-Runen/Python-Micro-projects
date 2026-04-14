"""
Stepwise path-aware farm build search and bounded beam (lane or jungle). See OPTIMIZATION_CRITERIA.md.

Purchase ranking blends **immediate** capped farm-tick marginals with **transitive** recipe-path
value toward high modeled-clear items (:func:`~LoLPerfmon.sim.item_heuristics.exploration_path_value_by_item`).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable, Literal

from .clear import effective_dps
from .config import FarmMode
from .data_loader import GameDataBundle
from .marginal_farm_tick import (
    marginal_clear_units_per_tick_derivative,
    marginal_farm_gold_per_tick_derivative,
)
from .models import ChampionProfile, ItemDef, is_build_endpoint_item, is_pure_shop_component
from .simulator import (
    MAX_INVENTORY_SLOTS,
    PurchasePolicy,
    SimResult,
    SimulationState,
    acquire_goal,
    inventory_count,
    simulate,
    try_acquire_with_lane_starter_sells,
    try_acquire_with_shop_sells,
)
from .stats import clamp_champion_level, total_stats
from .item_heuristics import exploration_path_value_by_item

MarginalTickObjective = Literal["farm_gold", "clear_count"]


def _level_weight_for_marginal_blend(level: int) -> float:
    """Higher at low champion level: weight farm-tick marginal more early, raw ΔDPS/gold more later."""
    if level >= 14:
        return 0.2
    return max(0.0, min(1.0, (14 - level) / 13.0))


def _min_max_unit_interval(values: list[float]) -> list[float]:
    """Map values to [0, 1]; constant inputs become 0.5 for stable blending."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-18:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def _try_marginal_acquire(
    trial: SimulationState,
    item_id: str,
    items: dict,
    *,
    allow_lane_starter_sell: bool,
    allow_sell_non_starter_items: bool,
) -> bool:
    if allow_sell_non_starter_items:
        return try_acquire_with_shop_sells(
            trial, item_id, items, allow_sell_non_starter_items=True
        )
    if allow_lane_starter_sell:
        return try_acquire_with_lane_starter_sells(trial, item_id, items)
    return acquire_goal(trial, item_id, items)

def _snapshot_state(s: SimulationState) -> SimulationState:
    return SimulationState(
        time_seconds=s.time_seconds,
        gold=s.gold,
        inventory=list(s.inventory),
        total_xp=s.total_xp,
        level=s.level,
        buy_queue=list(s.buy_queue),
        total_gold_spent_on_items=s.total_gold_spent_on_items,
        total_shop_sell_gold=s.total_shop_sell_gold,
        blocked_purchase_ids=set(s.blocked_purchase_ids),
    )


def _recipe_craft_burst(
    state: SimulationState,
    items: dict,
    order_sink: list[str] | None,
) -> None:
    """Apply any affordable recipe combines (parents with ``from_ids``) until none succeed in a pass."""
    while True:
        progressed = False
        for pid in sorted(items.keys()):
            it = items[pid]
            if not it.from_ids:
                continue
            if acquire_goal(state, pid, items):
                progressed = True
                if order_sink is not None:
                    order_sink.append(pid)
        if not progressed:
            break


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
    marginal_tick_objective: MarginalTickObjective = "farm_gold",
    endpoints_only_marginals: bool = False,
    allow_lane_starter_sell: bool = False,
    allow_sell_non_starter_items: bool = False,
    use_level_weighted_marginal: bool = False,
    marginal_candidate_ids: frozenset[str] | None = None,
    marginal_reference_level: int | None = None,
    path_into_weight: float = 0.45,
    ideal_target_top_k: int = 16,
    ideal_path_boost: float = 0.25,
    normalize_marginal_path_blend: bool = True,
) -> list[tuple[str, float, float, float]]:
    """
    One pass over ``items``: acquisitions that succeed on a snapshot and pass marginal rules.
    Returns tuples ``(item_id, score, delta_dps, gold_paid)`` unsorted.

    Score blends (1) **immediate** farm or clear marginal per gold paid with (2) **path** value:
    transitive max modeled ΔDPS/gold along ``into_ids`` toward top modeled-clear targets
    (:func:`~LoLPerfmon.sim.item_heuristics.exploration_path_value_by_item`), so components on
    routes to strong finishers are not ranked only by myopic ΔDPS from the cheap step alone.

    With ``allow_sell_non_starter_items``, trials use :func:`try_acquire_with_shop_sells`
    (lane starters first, then any item). With ``allow_lane_starter_sell`` only, trials use
    :func:`try_acquire_with_lane_starter_sells`.

    With ``marginal_income_cap`` and ``data`` set, the immediate term uses a first-order tick
    estimate ``(d tick_metric / d dps) * Δdps / gold_paid`` (capped throughput).

    With ``endpoints_only_marginals``, skips **pure shop components** (no ``from``, non-empty
    ``into``) so the shop only adds endpoints or recipe parents (``from_ids`` non-empty), i.e.
    full buys or crafts—not standalone Long Swords / Tomes.

    ``marginal_reference_level``: level for :func:`~LoLPerfmon.sim.item_heuristics.exploration_path_value_by_item`
    static path/ideal heuristics. ``None`` (default) uses the current sim level so champion
    base stat growth matches :func:`~LoLPerfmon.sim.stats.total_stats` at that level.

    When ``normalize_marginal_path_blend`` is True, **immediate** and **path** terms are
    min–max normalized across this candidate batch before combining so ``path_into_weight`` is
    a tradeoff on comparable [0, 1] scales (recommended when ``marginal_income_cap`` is True).
    """
    path_ref = (
        marginal_reference_level
        if marginal_reference_level is not None
        else clamp_champion_level(state.level)
    )
    path_val = exploration_path_value_by_item(
        profile,
        items,
        reference_level=path_ref,
        ideal_target_top_k=ideal_target_top_k,
        ideal_path_boost=ideal_path_boost,
    )
    base_stats = total_stats(profile, state.level, tuple(state.inventory), items)
    dps0 = effective_dps(profile, state.level, base_stats)
    dg_ddps = 0.0
    if marginal_income_cap and data is not None:
        if marginal_tick_objective == "clear_count":
            dg_ddps = marginal_clear_units_per_tick_derivative(data, farm_mode, eta_lane, profile, state)
        else:
            dg_ddps = marginal_farm_gold_per_tick_derivative(data, farm_mode, eta_lane, profile, state)
    raw_rows: list[tuple[str, float, float, float, float]] = []
    for iid in sorted(items.keys()):
        if marginal_candidate_ids is not None and iid not in marginal_candidate_ids:
            continue
        if iid in state.blocked_purchase_ids:
            continue
        it_def = items[iid]
        if endpoints_only_marginals and is_pure_shop_component(it_def):
            continue
        if inventory_count(state.inventory, iid) >= it_def.max_inventory_copies:
            continue
        trial = _snapshot_state(state)
        spent_before = trial.total_gold_spent_on_items
        ok = _try_marginal_acquire(
            trial,
            iid,
            items,
            allow_lane_starter_sell=allow_lane_starter_sell,
            allow_sell_non_starter_items=allow_sell_non_starter_items,
        )
        if not ok:
            continue
        paid = trial.total_gold_spent_on_items - spent_before
        st1 = total_stats(profile, trial.level, tuple(trial.inventory), items)
        dps1 = effective_dps(profile, trial.level, st1)
        delta = dps1 - dps0
        if delta <= 1e-15:
            continue
        denom = max(paid, epsilon)
        score_dps = delta / denom
        if marginal_income_cap and data is not None:
            marginal_tick = dg_ddps * delta
            if marginal_tick <= 1e-18:
                continue
            score_cap = marginal_tick / denom
            if use_level_weighted_marginal:
                w = _level_weight_for_marginal_blend(state.level)
                imm = w * score_cap + (1.0 - w) * score_dps
            else:
                imm = score_cap
        else:
            imm = score_dps
        pv = path_val.get(iid, 0.0)
        raw_rows.append((iid, imm, pv, delta, paid))

    out: list[tuple[str, float, float, float]] = []
    if not raw_rows:
        return out

    if normalize_marginal_path_blend and len(raw_rows) >= 1:
        imms = [r[1] for r in raw_rows]
        pvs = [r[2] for r in raw_rows]
        nim = _min_max_unit_interval(imms)
        npv = _min_max_unit_interval(pvs)
        for i, row in enumerate(raw_rows):
            iid, _imm, _pv, delta, paid = row
            score = nim[i] + path_into_weight * npv[i]
            out.append((iid, score, delta, paid))
        return out

    for iid, imm, pv, delta, paid in raw_rows:
        score = imm + path_into_weight * pv
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
    marginal_tick_objective: MarginalTickObjective = "farm_gold",
    endpoints_only_marginals: bool = False,
    allow_lane_starter_sell: bool = False,
    allow_sell_non_starter_items: bool = False,
    use_level_weighted_marginal: bool = False,
    marginal_candidate_ids: frozenset[str] | None = None,
    marginal_reference_level: int | None = None,
    path_into_weight: float = 0.45,
    ideal_target_top_k: int = 16,
    ideal_path_boost: float = 0.25,
    normalize_marginal_path_blend: bool = True,
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
        marginal_tick_objective=marginal_tick_objective,
        endpoints_only_marginals=endpoints_only_marginals,
        allow_lane_starter_sell=allow_lane_starter_sell,
        allow_sell_non_starter_items=allow_sell_non_starter_items,
        use_level_weighted_marginal=use_level_weighted_marginal,
        marginal_candidate_ids=marginal_candidate_ids,
        marginal_reference_level=marginal_reference_level,
        path_into_weight=path_into_weight,
        ideal_target_top_k=ideal_target_top_k,
        ideal_path_boost=ideal_path_boost,
        normalize_marginal_path_blend=normalize_marginal_path_blend,
    )
    cands.sort(key=lambda t: (-t[1], -t[2], t[0]))
    return cands


def _stepwise_purchase_burst(
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
    marginal_tick_objective: MarginalTickObjective = "farm_gold",
    endpoints_only_marginals: bool = False,
    allow_lane_starter_sell: bool = False,
    allow_sell_non_starter_items: bool = False,
    use_level_weighted_marginal: bool = False,
    marginal_candidate_ids: frozenset[str] | None = None,
    marginal_reference_level: int | None = None,
    path_into_weight: float = 0.45,
    ideal_target_top_k: int = 16,
    ideal_path_boost: float = 0.25,
    normalize_marginal_path_blend: bool = True,
) -> None:
    if defer_purchases_until is not None and state.time_seconds + 1e-9 < defer_purchases_until:
        return
    _recipe_craft_burst(state, items, order_sink)
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
            marginal_tick_objective=marginal_tick_objective,
            endpoints_only_marginals=endpoints_only_marginals,
            allow_lane_starter_sell=allow_lane_starter_sell,
            allow_sell_non_starter_items=allow_sell_non_starter_items,
            use_level_weighted_marginal=use_level_weighted_marginal,
            marginal_candidate_ids=marginal_candidate_ids,
            marginal_reference_level=marginal_reference_level,
            path_into_weight=path_into_weight,
            ideal_target_top_k=ideal_target_top_k,
            ideal_path_boost=ideal_path_boost,
            normalize_marginal_path_blend=normalize_marginal_path_blend,
        )
        best = _pick_best_marginal(cands)
        if best is None:
            break
        ok = _try_marginal_acquire(
            state,
            best,
            items,
            allow_lane_starter_sell=allow_lane_starter_sell,
            allow_sell_non_starter_items=allow_sell_non_starter_items,
        )
        if not ok:
            break
        if order_sink is not None:
            order_sink.append(best)
        _recipe_craft_burst(state, items, order_sink)


_greedy_purchase_burst = _stepwise_purchase_burst


def make_early_stop_full_inventory_no_dps_marginal(
    profile: ChampionProfile,
    items: dict,
    epsilon: float,
    *,
    data: GameDataBundle,
    farm_mode: FarmMode = FarmMode.LANE,
    eta_lane: float = 1.0,
    allow_lane_starter_sell: bool = True,
    allow_sell_non_starter_items: bool = False,
    use_level_weighted_marginal: bool = False,
    marginal_candidate_ids: frozenset[str] | None = None,
    marginal_reference_level: int | None = None,
    path_into_weight: float = 0.45,
    ideal_target_top_k: int = 16,
    ideal_path_boost: float = 0.25,
    normalize_marginal_path_blend: bool = True,
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
            allow_lane_starter_sell=allow_lane_starter_sell,
            allow_sell_non_starter_items=allow_sell_non_starter_items,
            use_level_weighted_marginal=use_level_weighted_marginal,
            marginal_candidate_ids=marginal_candidate_ids,
            marginal_reference_level=marginal_reference_level,
            path_into_weight=path_into_weight,
            ideal_target_top_k=ideal_target_top_k,
            ideal_path_boost=ideal_path_boost,
            normalize_marginal_path_blend=normalize_marginal_path_blend,
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


def make_stepwise_farm_hook(
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
    marginal_tick_objective: MarginalTickObjective = "farm_gold",
    endpoints_only_marginals: bool = False,
    allow_lane_starter_sell: bool = True,
    allow_sell_non_starter_items: bool = False,
    use_level_weighted_marginal: bool = False,
    marginal_candidate_ids: frozenset[str] | None = None,
    marginal_reference_level: int | None = None,
    path_into_weight: float = 0.45,
    ideal_target_top_k: int = 16,
    ideal_path_boost: float = 0.25,
    normalize_marginal_path_blend: bool = True,
) -> Callable[[SimulationState], None]:
    def purchase_hook(state: SimulationState) -> None:
        _stepwise_purchase_burst(
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
            marginal_tick_objective=marginal_tick_objective,
            endpoints_only_marginals=endpoints_only_marginals,
            allow_lane_starter_sell=allow_lane_starter_sell,
            allow_sell_non_starter_items=allow_sell_non_starter_items,
            use_level_weighted_marginal=use_level_weighted_marginal,
            marginal_candidate_ids=marginal_candidate_ids,
            marginal_reference_level=marginal_reference_level,
            path_into_weight=path_into_weight,
            ideal_target_top_k=ideal_target_top_k,
            ideal_path_boost=ideal_path_boost,
            normalize_marginal_path_blend=normalize_marginal_path_blend,
        )

    return purchase_hook


make_greedy_hook = make_stepwise_farm_hook
make_greedy_lane_hook = make_stepwise_farm_hook


def make_forced_prefix_then_stepwise_hook(
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
    marginal_tick_objective: MarginalTickObjective = "farm_gold",
    endpoints_only_marginals: bool = False,
    allow_lane_starter_sell: bool = True,
    allow_sell_non_starter_items: bool = False,
    use_level_weighted_marginal: bool = False,
    marginal_candidate_ids: frozenset[str] | None = None,
    marginal_reference_level: int | None = None,
    path_into_weight: float = 0.45,
    ideal_target_top_k: int = 16,
    ideal_path_boost: float = 0.25,
    normalize_marginal_path_blend: bool = True,
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
        _recipe_craft_burst(state, items, order_sink)
        _stepwise_purchase_burst(
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
            marginal_tick_objective=marginal_tick_objective,
            endpoints_only_marginals=endpoints_only_marginals,
            allow_lane_starter_sell=allow_lane_starter_sell,
            allow_sell_non_starter_items=allow_sell_non_starter_items,
            use_level_weighted_marginal=use_level_weighted_marginal,
            marginal_candidate_ids=marginal_candidate_ids,
            marginal_reference_level=marginal_reference_level,
            path_into_weight=path_into_weight,
            ideal_target_top_k=ideal_target_top_k,
            ideal_path_boost=ideal_path_boost,
            normalize_marginal_path_blend=normalize_marginal_path_blend,
        )

    return purchase_hook


make_forced_prefix_then_greedy_hook = make_forced_prefix_then_stepwise_hook


@dataclass(frozen=True)
class StepwiseFarmMetadata:
    epsilon: float
    purchase_count: int


GreedyFarmMetadata = StepwiseFarmMetadata


@dataclass(frozen=True)
class BeamFarmMetadata:
    beam_depth: int
    beam_width: int
    max_leaf_evals: int
    epsilon: float
    leaves_evaluated: int


def stepwise_farm_build(
    data: GameDataBundle,
    champion_id: str,
    eta_lane: float = 1.0,
    t_max: float | None = None,
    defer_purchases_until: float | None = None,
    epsilon: float = 1e-9,
    farm_mode: FarmMode = FarmMode.LANE,
    jungle_starter_item_id: str | None = None,
    marginal_income_cap: bool = True,
    allow_lane_starter_sell: bool = True,
    allow_sell_non_starter_items: bool = False,
    use_level_weighted_marginal: bool = False,
    meaningful_exploration: bool = False,
    marginal_candidate_ids: frozenset[str] | None = None,
    marginal_reference_level: int | None = None,
    path_into_weight: float = 0.45,
    ideal_target_top_k: int = 16,
    ideal_path_boost: float = 0.25,
    normalize_marginal_path_blend: bool = True,
    marginal_objective: Literal["dps_per_gold", "horizon_greedy_roi"] = "horizon_greedy_roi",
    horizon_candidate_cap: int = 128,
    allow_full_catalog_fallback: bool = False,
) -> tuple[tuple[str, ...], float, SimResult, BeamFarmMetadata | StepwiseFarmMetadata]:
    """
    Single-step beam (``beam_depth=1``, ``beam_width=1``) with path-aware stepwise shop policy.
    Prefer :func:`beam_refined_farm_build` for deeper prefixes. ``meaningful_exploration`` narrows
    marginal candidates via :func:`~LoLPerfmon.sim.item_heuristics.meaningful_waveclear_exploration_catalog`.
    """
    profile = data.champions[champion_id]
    mc_ids = marginal_candidate_ids
    if meaningful_exploration and mc_ids is None:
        from .item_heuristics import waveclear_relevant_item_catalog

        cat_lv = 11 if marginal_reference_level is None else marginal_reference_level
        mc_ids = frozenset(
            waveclear_relevant_item_catalog(
                data.items,
                farm_mode,
                profile,
                reference_level=cat_lv,
                allow_full_catalog_fallback=allow_full_catalog_fallback,
            ).keys()
        )
    return beam_refined_farm_build(
        data,
        champion_id,
        eta_lane=eta_lane,
        t_max=t_max,
        defer_purchases_until=defer_purchases_until,
        epsilon=epsilon,
        beam_depth=1,
        beam_width=1,
        max_leaf_evals=8,
        farm_mode=farm_mode,
        marginal_objective=marginal_objective,
        horizon_candidate_cap=horizon_candidate_cap,
        jungle_starter_item_id=jungle_starter_item_id,
        marginal_income_cap=marginal_income_cap,
        allow_lane_starter_sell=allow_lane_starter_sell,
        allow_sell_non_starter_items=allow_sell_non_starter_items,
        use_level_weighted_marginal=use_level_weighted_marginal,
        meaningful_exploration=False,
        marginal_candidate_ids=mc_ids,
        marginal_reference_level=marginal_reference_level,
        path_into_weight=path_into_weight,
        ideal_target_top_k=ideal_target_top_k,
        ideal_path_boost=ideal_path_boost,
        normalize_marginal_path_blend=normalize_marginal_path_blend,
        allow_full_catalog_fallback=allow_full_catalog_fallback,
    )


def beam_refined_farm_build(
    data: GameDataBundle,
    champion_id: str,
    eta_lane: float = 1.0,
    t_max: float | None = None,
    defer_purchases_until: float | None = None,
    epsilon: float = 1e-9,
    beam_depth: int = 8,
    beam_width: int = 64,
    beam_branching_width: int | None = None,
    beam_survivors: int | None = None,
    max_leaf_evals: int = 512,
    farm_mode: FarmMode = FarmMode.LANE,
    marginal_objective: Literal["dps_per_gold", "horizon_greedy_roi"] = "horizon_greedy_roi",
    horizon_candidate_cap: int = 128,
    jungle_starter_item_id: str | None = None,
    marginal_income_cap: bool = True,
    leaf_score: Literal[
        "total_farm_gold", "early_dps_auc", "farm_gold_per_gold_spent", "total_clear_units"
    ] = "total_farm_gold",
    early_horizon_seconds: float = 900.0,
    early_stop: Callable[[SimulationState], bool] | None = None,
    extrapolate_lane_waves: bool | None = None,
    endpoints_only_marginals: bool = False,
    allow_lane_starter_sell: bool = True,
    allow_sell_non_starter_items: bool = False,
    use_level_weighted_marginal: bool = False,
    marginal_tick_objective: MarginalTickObjective = "farm_gold",
    meaningful_exploration: bool = True,
    marginal_candidate_ids: frozenset[str] | None = None,
    meaningful_exclude_tags: frozenset[str] | None = None,
    meaningful_require_tags: frozenset[str] | None = None,
    marginal_reference_level: int | None = None,
    path_into_weight: float = 0.45,
    ideal_target_top_k: int = 16,
    ideal_path_boost: float = 0.25,
    normalize_marginal_path_blend: bool = True,
    allow_full_catalog_fallback: bool = False,
) -> tuple[tuple[str, ...], float, SimResult, BeamFarmMetadata | StepwiseFarmMetadata]:
    """
    Beam search over purchase prefixes (depth ``beam_depth``, width ``beam_width``).
    Default leaf score is full-horizon ``total_farm_gold``; use ``leaf_score='early_dps_auc'``
    to maximize ∫ modeled effective DPS dt over ``early_horizon_seconds``. Path-aware stepwise
    tail after each prefix (see :func:`make_stepwise_farm_hook`).

    Pass ``early_stop`` and ``t_max=float('inf')`` (e.g. with
    :func:`make_early_stop_six_build_endpoints`) to run until a custom stop condition; set
    ``extrapolate_lane_waves=True`` when the horizon can exceed the bundle wave list.
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
        beam_branching_width=beam_branching_width,
        beam_survivors=beam_survivors,
        max_leaf_evals=max_leaf_evals,
        marginal_objective=marginal_objective,
        horizon_candidate_cap=horizon_candidate_cap,
        jungle_starter_item_id=jungle_starter_item_id,
        marginal_income_cap=marginal_income_cap,
        marginal_tick_objective=marginal_tick_objective,
        leaf_score=leaf_score,
        early_horizon_seconds=early_horizon_seconds,
        early_stop=early_stop,
        extrapolate_lane_waves=extrapolate_lane_waves,
        endpoints_only_marginals=endpoints_only_marginals,
        allow_lane_starter_sell=allow_lane_starter_sell,
        allow_sell_non_starter_items=allow_sell_non_starter_items,
        use_level_weighted_marginal=use_level_weighted_marginal,
        meaningful_exploration=meaningful_exploration,
        marginal_candidate_ids=marginal_candidate_ids,
        meaningful_exclude_tags=meaningful_exclude_tags,
        meaningful_require_tags=meaningful_require_tags,
        marginal_reference_level=marginal_reference_level,
        path_into_weight=path_into_weight,
        ideal_target_top_k=ideal_target_top_k,
        ideal_path_boost=ideal_path_boost,
        normalize_marginal_path_blend=normalize_marginal_path_blend,
        allow_full_catalog_fallback=allow_full_catalog_fallback,
    )
    return search.run()


__all__ = [
    "MarginalTickObjective",
    "BeamFarmMetadata",
    "GreedyFarmMetadata",
    "StepwiseFarmMetadata",
    "beam_refined_farm_build",
    "ranked_marginal_acquisitions",
    "stepwise_farm_build",
    "make_early_stop_full_inventory_no_dps_marginal",
    "make_early_stop_six_build_endpoints",
    "make_forced_prefix_then_greedy_hook",
    "make_forced_prefix_then_stepwise_hook",
    "make_greedy_hook",
    "make_greedy_lane_hook",
    "make_stepwise_farm_hook",
]
