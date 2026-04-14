"""
Bounded beam search over purchase prefixes for farm builds. See OPTIMIZATION_CRITERIA.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from .item_heuristics import filter_waveclear_item_catalog, waveclear_relevant_item_catalog

from .config import FarmMode
from .data_loader import GameDataBundle
from .models import ChampionProfile
from .jungle_items import resolve_jungle_starter_item_id
from .simulator import (
    PurchasePolicy,
    SimResult,
    SimulationState,
    acquire_goal,
    default_clear_count_score,
    simulate,
)
from .greedy_farm_build import (
    BeamFarmMetadata,
    MarginalTickObjective,
    StepwiseFarmMetadata,
    make_forced_prefix_then_stepwise_hook,
    make_stepwise_farm_hook,
    ranked_marginal_acquisitions,
)
from .purchase_metrics import auc_effective_dps_piecewise


def _waveclear_catalog_reference_level(marginal_reference_level: int | None) -> int:
    """Level for DPS gate and stat-axis catalog; aligns with typical path heuristics (mid-game)."""
    return 11 if marginal_reference_level is None else marginal_reference_level


MarginalObjective = Literal["dps_per_gold", "horizon_greedy_roi"]
LeafScore = Literal["total_farm_gold", "early_dps_auc", "farm_gold_per_gold_spent", "total_clear_units"]


def _leaf_primary_value(
    res: SimResult, leaf_score: LeafScore, farm_mode: FarmMode, epsilon: float
) -> float:
    if leaf_score == "farm_gold_per_gold_spent":
        return _farm_gold_per_gold_spent(res, epsilon)
    if leaf_score == "total_clear_units":
        return default_clear_count_score(res, farm_mode)
    return res.total_farm_gold


def _farm_gold_per_gold_spent(res: SimResult, epsilon: float) -> float:
    """Modeled farm income per gold paid to shop (higher = better return on item spend)."""
    denom = max(res.total_gold_spent_on_items, epsilon)
    return res.total_farm_gold / denom


def _simulate_greedy_hook_early_dps_auc(
    data: GameDataBundle,
    champion_id: str,
    farm_mode: FarmMode,
    eta_lane: float,
    t_max: float | None,
    defer_purchases_until: float | None,
    purchase_hook,
    early_horizon: float,
    jungle_starter_item_id: str | None,
    early_stop: Callable[[SimulationState], bool] | None = None,
    extrapolate_lane_waves: bool | None = None,
) -> tuple[float, SimResult]:
    samples: list[tuple[float, float]] = []

    def lane_cb(t: float, _k: int, dps: float) -> None:
        samples.append((t, float(dps)))

    def jungle_cb(t: float, _k: int, dps: float) -> None:
        samples.append((t, float(dps)))

    res = simulate(
        data,
        champion_id,
        farm_mode,
        PurchasePolicy(buy_order=()),
        eta_lane=eta_lane,
        t_max=t_max,
        defer_purchases_until=defer_purchases_until,
        purchase_hook=purchase_hook,
        on_lane_clear_dps=lane_cb if farm_mode == FarmMode.LANE else None,
        on_jungle_clear_dps=jungle_cb if farm_mode == FarmMode.JUNGLE else None,
        jungle_starter_item_id=jungle_starter_item_id,
        early_stop=early_stop,
        extrapolate_lane_waves=extrapolate_lane_waves,
    )
    return auc_effective_dps_piecewise(samples, early_horizon), res


def initial_farm_state(
    data: GameDataBundle,
    farm_mode: FarmMode,
    jungle_starter_item_id: str | None,
) -> SimulationState:
    st = SimulationState(
        time_seconds=0.0,
        gold=float(data.rules.start_gold),
        inventory=[],
        total_xp=0.0,
        level=1,
        buy_queue=[],
        total_gold_spent_on_items=0.0,
        blocked_purchase_ids=set(),
    )
    if farm_mode == FarmMode.JUNGLE:
        sid = resolve_jungle_starter_item_id(data, jungle_starter_item_id)
        if not acquire_goal(st, sid, data.items):
            raise ValueError(
                f"Jungle starter {sid} could not be applied at t=0 (gold={st.gold})."
            )
    return st


def state_after_prefix(
    data: GameDataBundle,
    items: dict,
    prefix: tuple[str, ...],
    farm_mode: FarmMode = FarmMode.LANE,
    jungle_starter_item_id: str | None = None,
) -> SimulationState | None:
    st = initial_farm_state(data, farm_mode, jungle_starter_item_id)
    for pid in prefix:
        if pid not in items:
            return None
        if not acquire_goal(st, pid, items):
            return None
    return st


def _ranked_horizon_next_items(
    data: GameDataBundle,
    champion_id: str,
    farm_mode: FarmMode,
    profile: ChampionProfile,
    items: dict,
    eta_lane: float,
    t_max: float | None,
    defer_purchases_until: float | None,
    epsilon: float,
    baseline_res: SimResult,
    state: SimulationState,
    horizon_candidate_cap: int,
    jungle_starter_item_id: str | None,
    marginal_income_cap: bool,
    marginal_tick_objective: MarginalTickObjective,
    leaf_score: LeafScore,
    early_stop: Callable[[SimulationState], bool] | None = None,
    extrapolate_lane_waves: bool | None = None,
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
) -> list[tuple[str, float, float, float]]:
    """Rank next purchases by Δleaf_primary vs baseline stepwise hook (nested full sims)."""
    dps_ranked = ranked_marginal_acquisitions(
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
    cap = max(horizon_candidate_cap, 4)
    candidate_ids = [r[0] for r in dps_ranked[:cap]]
    if not candidate_ids:
        return []
    rows: list[tuple[str, float, float, float]] = []
    for iid in candidate_ids:
        order_i: list[str] = []
        hook_f = make_forced_prefix_then_stepwise_hook(
            profile,
            items,
            defer_purchases_until,
            epsilon,
            (iid,),
            order_sink=order_i,
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
        res_i = simulate(
            data,
            champion_id,
            farm_mode,
            PurchasePolicy(buy_order=()),
            eta_lane=eta_lane,
            t_max=t_max,
            defer_purchases_until=defer_purchases_until,
            purchase_hook=hook_f,
            jungle_starter_item_id=jungle_starter_item_id,
            early_stop=early_stop,
            extrapolate_lane_waves=extrapolate_lane_waves,
        )
        delta_primary = _leaf_primary_value(res_i, leaf_score, farm_mode, epsilon) - _leaf_primary_value(
            baseline_res, leaf_score, farm_mode, epsilon
        )
        paid = items[iid].total_cost if iid in items else 0.0
        score = delta_primary / max(paid, epsilon)
        rows.append((iid, score, delta_primary, paid))
    rows.sort(key=lambda t: (-t[1], -t[2], t[0]))
    return rows


def _marginals_for_beam_step(
    data: GameDataBundle,
    champion_id: str,
    farm_mode: FarmMode,
    profile: ChampionProfile,
    items: dict,
    prefix: tuple[str, ...],
    eta_lane: float,
    t_max: float | None,
    defer_purchases_until: float | None,
    epsilon: float,
    marginal_objective: MarginalObjective,
    baseline_res: SimResult | None,
    horizon_candidate_cap: int,
    jungle_starter_item_id: str | None = None,
    marginal_income_cap: bool = True,
    marginal_tick_objective: MarginalTickObjective = "farm_gold",
    leaf_score: LeafScore = "total_farm_gold",
    early_stop: Callable[[SimulationState], bool] | None = None,
    extrapolate_lane_waves: bool | None = None,
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
) -> list[tuple[str, float, float, float]]:
    st = state_after_prefix(data, items, prefix, farm_mode, jungle_starter_item_id)
    if st is None:
        return []
    margs_kw = dict(
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
    if prefix:
        return ranked_marginal_acquisitions(st, profile, items, epsilon, **margs_kw)
    if marginal_objective == "horizon_greedy_roi" and baseline_res is not None:
        return _ranked_horizon_next_items(
            data,
            champion_id,
            farm_mode,
            profile,
            items,
            eta_lane,
            t_max,
            defer_purchases_until,
            epsilon,
            baseline_res,
            st,
            horizon_candidate_cap,
            jungle_starter_item_id,
            marginal_income_cap,
            marginal_tick_objective,
            leaf_score,
            early_stop,
            extrapolate_lane_waves,
            endpoints_only_marginals,
            allow_lane_starter_sell,
            allow_sell_non_starter_items,
            use_level_weighted_marginal,
            marginal_candidate_ids,
            marginal_reference_level,
            path_into_weight,
            ideal_target_top_k,
            ideal_path_boost,
            normalize_marginal_path_blend,
        )
    return ranked_marginal_acquisitions(st, profile, items, epsilon, **margs_kw)


@dataclass
class FarmBuildSearch:
    """
    Beam search over purchase prefixes. Default leaf score is full-horizon ``total_farm_gold``;
    set ``leaf_score='early_dps_auc'`` to maximize ∫ effective_dps dt over ``early_horizon_seconds``;
    set ``leaf_score='farm_gold_per_gold_spent'`` to maximize ``total_farm_gold / total_gold_spent_on_items``.
    Set ``leaf_score='total_clear_units'`` to maximize lane minions or jungle monsters cleared
    (uses :func:`~LoLPerfmon.sim.simulator.default_clear_count_score`; greedy marginals use clear-count
    tick derivatives unless overridden by ``marginal_tick_objective``).
    """

    data: GameDataBundle
    champion_id: str
    farm_mode: FarmMode = FarmMode.LANE
    eta_lane: float = 1.0
    t_max: float | None = None
    defer_purchases_until: float | None = None
    epsilon: float = 1e-9
    beam_depth: int = 8
    beam_width: int = 64
    #: Marginal expansions considered from each prefix. Defaults to ``beam_width`` when unset.
    beam_branching_width: int | None = None
    #: Number of prefixes kept after each depth. Defaults to ``beam_width`` when unset.
    beam_survivors: int | None = None
    max_leaf_evals: int = 512
    marginal_objective: MarginalObjective = "horizon_greedy_roi"
    horizon_candidate_cap: int = 128
    #: Required for :class:`FarmMode.JUNGLE` beam prefix snapshots (same starter as :func:`simulate`).
    jungle_starter_item_id: str | None = None
    #: If True, greedy marginals skip purchases with negligible marginal farm gold (capped throughput).
    marginal_income_cap: bool = True
    #: ``farm_gold`` vs ``clear_count`` tick derivative for capped marginals (see :mod:`marginal_farm_tick`).
    marginal_tick_objective: MarginalTickObjective = "farm_gold"
    leaf_score: LeafScore = "total_farm_gold"
    #: Upper bound of ∫ DPS dt when ``leaf_score == 'early_dps_auc'`` (seconds of simulated time).
    early_horizon_seconds: float = 900.0
    #: If set, passed to :func:`simulate` (e.g. stop when six build-endpoint items fill the bag).
    early_stop: Callable[[SimulationState], bool] | None = None
    #: Passed to :func:`simulate`; ``None`` means infer from ``t_max`` (see simulator).
    extrapolate_lane_waves: bool | None = None
    #: If True, greedy/beam marginals skip standalone components (Long Sword, Tome, …); only endpoints or recipe parents.
    endpoints_only_marginals: bool = False
    #: If True, greedy hooks may sell Doran's / Dark Seal / … to afford or fit the next marginal buy.
    allow_lane_starter_sell: bool = True
    #: If True, after lane starters, greedy may sell any inventory item (50% refund) to afford a buy.
    allow_sell_non_starter_items: bool = False
    #: Blend farm-tick marginal with raw ΔDPS/gold by champion level (see :mod:`greedy_farm_build`).
    use_level_weighted_marginal: bool = False
    #: If True and ``marginal_candidate_ids`` is None, restrict greedy/beam marginals to
    #: :func:`~LoLPerfmon.sim.item_heuristics.meaningful_waveclear_exploration_catalog`.
    meaningful_exploration: bool = True
    #: Optional explicit allow-list for marginal purchase attempts (full ``data.items`` still used for crafts).
    marginal_candidate_ids: frozenset[str] | None = None
    #: Passed to :func:`~LoLPerfmon.sim.item_heuristics.meaningful_waveclear_exploration_catalog` when meaningful.
    meaningful_exclude_tags: frozenset[str] | None = None
    meaningful_require_tags: frozenset[str] | None = None
    #: Fixed level for path/ideal static heuristics; ``None`` uses current sim level (clamped 1–18).
    marginal_reference_level: int | None = None
    #: Weight on transitive ``into_ids`` path value (:func:`~LoLPerfmon.sim.item_heuristics.exploration_path_value_by_item`).
    path_into_weight: float = 0.45
    #: Top-``k`` items by modeled ΔDPS seed “ideal clear” targets for path boost.
    ideal_target_top_k: int = 16
    #: Multiplier when a path reaches an ideal target (see :func:`exploration_path_value_by_item`).
    ideal_path_boost: float = 0.25
    #: Min–max normalize immediate vs path terms before blending in greedy marginals.
    normalize_marginal_path_blend: bool = True
    #: If True, waveclear candidate derivation may fall back to tag-filtered full catalog.
    allow_full_catalog_fallback: bool = False

    def run(self) -> tuple[tuple[str, ...], float, SimResult, BeamFarmMetadata | StepwiseFarmMetadata]:
        profile = self.data.champions[self.champion_id]
        items = self.data.items
        d = max(1, self.beam_depth)
        branch_w = max(1, self.beam_branching_width or self.beam_width)
        surv_w = max(1, self.beam_survivors or self.beam_width)
        eff_mtick: MarginalTickObjective = (
            "clear_count" if self.leaf_score == "total_clear_units" else self.marginal_tick_objective
        )

        mc_ids = self.marginal_candidate_ids
        if self.meaningful_exploration and mc_ids is None:
            cat = waveclear_relevant_item_catalog(
                self.data.items,
                self.farm_mode,
                profile,
                exclude_tags=self.meaningful_exclude_tags,
                require_tags=self.meaningful_require_tags,
                reference_level=_waveclear_catalog_reference_level(self.marginal_reference_level),
                allow_full_catalog_fallback=self.allow_full_catalog_fallback,
            )
            if not cat and self.allow_full_catalog_fallback:
                cat = filter_waveclear_item_catalog(
                    self.data.items,
                    self.farm_mode,
                    exclude_tags=self.meaningful_exclude_tags,
                    require_tags=self.meaningful_require_tags,
                )
            mc_ids = frozenset(cat.keys())

        order_g: list[str] = []
        hook_g = make_stepwise_farm_hook(
            profile,
            items,
            self.defer_purchases_until,
            self.epsilon,
            order_sink=order_g,
            data=self.data,
            farm_mode=self.farm_mode,
            eta_lane=self.eta_lane,
            marginal_income_cap=self.marginal_income_cap,
            marginal_tick_objective=eff_mtick,
            endpoints_only_marginals=self.endpoints_only_marginals,
            allow_lane_starter_sell=self.allow_lane_starter_sell,
            allow_sell_non_starter_items=self.allow_sell_non_starter_items,
            use_level_weighted_marginal=self.use_level_weighted_marginal,
            marginal_candidate_ids=mc_ids,
            marginal_reference_level=self.marginal_reference_level,
            path_into_weight=self.path_into_weight,
            ideal_target_top_k=self.ideal_target_top_k,
            ideal_path_boost=self.ideal_path_boost,
            normalize_marginal_path_blend=self.normalize_marginal_path_blend,
        )
        if self.leaf_score == "early_dps_auc":
            best_val, res_g = _simulate_greedy_hook_early_dps_auc(
                self.data,
                self.champion_id,
                self.farm_mode,
                self.eta_lane,
                self.t_max,
                self.defer_purchases_until,
                hook_g,
                self.early_horizon_seconds,
                self.jungle_starter_item_id,
                early_stop=self.early_stop,
                extrapolate_lane_waves=self.extrapolate_lane_waves,
            )
        else:
            res_g = simulate(
                self.data,
                self.champion_id,
                self.farm_mode,
                PurchasePolicy(buy_order=()),
                eta_lane=self.eta_lane,
                t_max=self.t_max,
                defer_purchases_until=self.defer_purchases_until,
                purchase_hook=hook_g,
                jungle_starter_item_id=self.jungle_starter_item_id,
                early_stop=self.early_stop,
                extrapolate_lane_waves=self.extrapolate_lane_waves,
            )
            if self.leaf_score == "farm_gold_per_gold_spent":
                best_val = _farm_gold_per_gold_spent(res_g, self.epsilon)
            elif self.leaf_score == "total_clear_units":
                best_val = default_clear_count_score(res_g, self.farm_mode)
            else:
                best_val = res_g.total_farm_gold
        leaves_evaluated = 1
        best_res = res_g
        best_order = tuple(order_g)

        first_margs = _marginals_for_beam_step(
            self.data,
            self.champion_id,
            self.farm_mode,
            profile,
            items,
            (),
            self.eta_lane,
            self.t_max,
            self.defer_purchases_until,
            self.epsilon,
            self.marginal_objective,
            res_g,
            self.horizon_candidate_cap,
            self.jungle_starter_item_id,
            self.marginal_income_cap,
            eff_mtick,
            self.leaf_score,
            self.early_stop,
            self.extrapolate_lane_waves,
            self.endpoints_only_marginals,
            self.allow_lane_starter_sell,
            self.allow_sell_non_starter_items,
            self.use_level_weighted_marginal,
            mc_ids,
            self.marginal_reference_level,
            self.path_into_weight,
            self.ideal_target_top_k,
            self.ideal_path_boost,
            self.normalize_marginal_path_blend,
        )
        if not first_margs:
            meta = StepwiseFarmMetadata(epsilon=self.epsilon, purchase_count=len(best_order))
            return best_order, best_val, best_res, meta

        beam_prefixes: list[tuple[str, ...]] = [()]
        for depth in range(1, d + 1):
            children_scores: list[tuple[tuple[str, ...], float, SimResult, tuple[str, ...]]] = []
            for prefix in beam_prefixes:
                if leaves_evaluated >= self.max_leaf_evals:
                    break
                margs = _marginals_for_beam_step(
                    self.data,
                    self.champion_id,
                    self.farm_mode,
                    profile,
                    items,
                    prefix,
                    self.eta_lane,
                    self.t_max,
                    self.defer_purchases_until,
                    self.epsilon,
                    self.marginal_objective,
                    res_g,
                    self.horizon_candidate_cap,
                    self.jungle_starter_item_id,
                    self.marginal_income_cap,
                    eff_mtick,
                    self.leaf_score,
                    self.early_stop,
                    self.extrapolate_lane_waves,
                    self.endpoints_only_marginals,
                    self.allow_lane_starter_sell,
                    self.allow_sell_non_starter_items,
                    self.use_level_weighted_marginal,
                    mc_ids,
                    self.marginal_reference_level,
                    self.path_into_weight,
                    self.ideal_target_top_k,
                    self.ideal_path_boost,
                    self.normalize_marginal_path_blend,
                )
                for row in margs[:branch_w]:
                    next_id = row[0]
                    if leaves_evaluated >= self.max_leaf_evals:
                        break
                    new_prefix = prefix + (next_id,)
                    order_i: list[str] = []
                    hook_f = make_forced_prefix_then_stepwise_hook(
                        profile,
                        items,
                        self.defer_purchases_until,
                        self.epsilon,
                        new_prefix,
                        order_sink=order_i,
                        data=self.data,
                        farm_mode=self.farm_mode,
                        eta_lane=self.eta_lane,
                        marginal_income_cap=self.marginal_income_cap,
                        marginal_tick_objective=eff_mtick,
                        endpoints_only_marginals=self.endpoints_only_marginals,
                        allow_lane_starter_sell=self.allow_lane_starter_sell,
                        allow_sell_non_starter_items=self.allow_sell_non_starter_items,
                        use_level_weighted_marginal=self.use_level_weighted_marginal,
                        marginal_candidate_ids=mc_ids,
                        marginal_reference_level=self.marginal_reference_level,
                        path_into_weight=self.path_into_weight,
                        ideal_target_top_k=self.ideal_target_top_k,
                        ideal_path_boost=self.ideal_path_boost,
                        normalize_marginal_path_blend=self.normalize_marginal_path_blend,
                    )
                    if self.leaf_score == "early_dps_auc":
                        fv, res_i = _simulate_greedy_hook_early_dps_auc(
                            self.data,
                            self.champion_id,
                            self.farm_mode,
                            self.eta_lane,
                            self.t_max,
                            self.defer_purchases_until,
                            hook_f,
                            self.early_horizon_seconds,
                            self.jungle_starter_item_id,
                            early_stop=self.early_stop,
                            extrapolate_lane_waves=self.extrapolate_lane_waves,
                        )
                    else:
                        res_i = simulate(
                            self.data,
                            self.champion_id,
                            self.farm_mode,
                            PurchasePolicy(buy_order=()),
                            eta_lane=self.eta_lane,
                            t_max=self.t_max,
                            defer_purchases_until=self.defer_purchases_until,
                            purchase_hook=hook_f,
                            jungle_starter_item_id=self.jungle_starter_item_id,
                            early_stop=self.early_stop,
                            extrapolate_lane_waves=self.extrapolate_lane_waves,
                        )
                        if self.leaf_score == "farm_gold_per_gold_spent":
                            fv = _farm_gold_per_gold_spent(res_i, self.epsilon)
                        elif self.leaf_score == "total_clear_units":
                            fv = default_clear_count_score(res_i, self.farm_mode)
                        else:
                            fv = res_i.total_farm_gold
                    leaves_evaluated += 1
                    tup = tuple(order_i)
                    children_scores.append((new_prefix, fv, res_i, tup))
                    if fv > best_val + 1e-9:
                        best_val = fv
                        best_res = res_i
                        best_order = tup
            if not children_scores:
                break
            children_scores.sort(key=lambda x: (-x[1], x[0]))
            beam_prefixes = [c[0] for c in children_scores[:surv_w]]

        meta = BeamFarmMetadata(
            beam_depth=d,
            beam_width=surv_w,
            max_leaf_evals=self.max_leaf_evals,
            epsilon=self.epsilon,
            leaves_evaluated=leaves_evaluated,
        )
        return best_order, best_val, best_res, meta


__all__ = [
    "FarmBuildSearch",
    "LeafScore",
    "MarginalObjective",
    "initial_farm_state",
    "state_after_prefix",
]
