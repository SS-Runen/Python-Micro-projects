"""
Bounded beam search over purchase prefixes for farm builds. See OPTIMIZATION_CRITERIA.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from .config import FarmMode
from .data_loader import GameDataBundle
from .models import ChampionProfile
from .jungle_items import resolve_jungle_starter_item_id
from .simulator import PurchasePolicy, SimResult, SimulationState, acquire_goal, simulate
from .greedy_farm_build import (
    BeamFarmMetadata,
    GreedyFarmMetadata,
    make_forced_prefix_then_greedy_hook,
    make_greedy_hook,
    ranked_marginal_acquisitions,
)
from .purchase_metrics import auc_effective_dps_piecewise

MarginalObjective = Literal["dps_per_gold", "horizon_greedy_roi"]
LeafScore = Literal["total_farm_gold", "early_dps_auc", "farm_gold_per_gold_spent"]


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
    early_stop: Callable[[SimulationState], bool] | None = None,
    extrapolate_lane_waves: bool | None = None,
    endpoints_only_marginals: bool = False,
    allow_lane_starter_sell: bool = True,
) -> list[tuple[str, float, float, float]]:
    """Rank next purchases by Δtotal_farm_gold vs baseline greedy (nested full sims)."""
    dps_ranked = ranked_marginal_acquisitions(
        state,
        profile,
        items,
        epsilon,
        data=data,
        farm_mode=farm_mode,
        eta_lane=eta_lane,
        marginal_income_cap=marginal_income_cap,
        endpoints_only_marginals=endpoints_only_marginals,
    )
    cap = max(horizon_candidate_cap, 4)
    candidate_ids = [r[0] for r in dps_ranked[:cap]]
    if not candidate_ids:
        return []
    rows: list[tuple[str, float, float, float]] = []
    for iid in candidate_ids:
        order_i: list[str] = []
        hook_f = make_forced_prefix_then_greedy_hook(
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
            endpoints_only_marginals=endpoints_only_marginals,
            allow_lane_starter_sell=allow_lane_starter_sell,
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
        delta_farm = res_i.total_farm_gold - baseline_res.total_farm_gold
        paid = items[iid].total_cost if iid in items else 0.0
        score = delta_farm / max(paid, epsilon)
        rows.append((iid, score, delta_farm, paid))
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
    early_stop: Callable[[SimulationState], bool] | None = None,
    extrapolate_lane_waves: bool | None = None,
    endpoints_only_marginals: bool = False,
    allow_lane_starter_sell: bool = True,
) -> list[tuple[str, float, float, float]]:
    st = state_after_prefix(data, items, prefix, farm_mode, jungle_starter_item_id)
    if st is None:
        return []
    margs_kw = dict(
        data=data,
        farm_mode=farm_mode,
        eta_lane=eta_lane,
        marginal_income_cap=marginal_income_cap,
        endpoints_only_marginals=endpoints_only_marginals,
        allow_lane_starter_sell=allow_lane_starter_sell,
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
            early_stop,
            extrapolate_lane_waves,
            endpoints_only_marginals,
            allow_lane_starter_sell,
        )
    return ranked_marginal_acquisitions(st, profile, items, epsilon, **margs_kw)


@dataclass
class FarmBuildSearch:
    """
    Beam search over purchase prefixes. Default leaf score is full-horizon ``total_farm_gold``;
    set ``leaf_score='early_dps_auc'`` to maximize ∫ effective_dps dt over ``early_horizon_seconds``;
    set ``leaf_score='farm_gold_per_gold_spent'`` to maximize ``total_farm_gold / total_gold_spent_on_items``.
    """

    data: GameDataBundle
    champion_id: str
    farm_mode: FarmMode = FarmMode.LANE
    eta_lane: float = 1.0
    t_max: float | None = None
    defer_purchases_until: float | None = None
    epsilon: float = 1e-9
    beam_depth: int = 1
    beam_width: int = 3
    max_leaf_evals: int = 27
    marginal_objective: MarginalObjective = "dps_per_gold"
    horizon_candidate_cap: int = 48
    #: Required for :class:`FarmMode.JUNGLE` beam prefix snapshots (same starter as :func:`simulate`).
    jungle_starter_item_id: str | None = None
    #: If True, greedy marginals skip purchases with negligible marginal farm gold (capped throughput).
    marginal_income_cap: bool = True
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

    def run(self) -> tuple[tuple[str, ...], float, SimResult, BeamFarmMetadata | GreedyFarmMetadata]:
        profile = self.data.champions[self.champion_id]
        items = self.data.items
        d = max(1, self.beam_depth)
        w = max(1, self.beam_width)

        order_g: list[str] = []
        hook_g = make_greedy_hook(
            profile,
            items,
            self.defer_purchases_until,
            self.epsilon,
            order_sink=order_g,
            data=self.data,
            farm_mode=self.farm_mode,
            eta_lane=self.eta_lane,
            marginal_income_cap=self.marginal_income_cap,
            endpoints_only_marginals=self.endpoints_only_marginals,
            allow_lane_starter_sell=self.allow_lane_starter_sell,
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
            self.early_stop,
            self.extrapolate_lane_waves,
            self.endpoints_only_marginals,
            self.allow_lane_starter_sell,
        )
        if not first_margs:
            meta = GreedyFarmMetadata(epsilon=self.epsilon, purchase_count=len(best_order))
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
                    self.early_stop,
                    self.extrapolate_lane_waves,
                    self.endpoints_only_marginals,
                    self.allow_lane_starter_sell,
                )
                for row in margs[:w]:
                    next_id = row[0]
                    if leaves_evaluated >= self.max_leaf_evals:
                        break
                    new_prefix = prefix + (next_id,)
                    order_i: list[str] = []
                    hook_f = make_forced_prefix_then_greedy_hook(
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
                        endpoints_only_marginals=self.endpoints_only_marginals,
                        allow_lane_starter_sell=self.allow_lane_starter_sell,
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
            children_scores.sort(key=lambda x: -x[1])
            beam_prefixes = [c[0] for c in children_scores[:w]]

        meta = BeamFarmMetadata(
            beam_depth=d,
            beam_width=w,
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
