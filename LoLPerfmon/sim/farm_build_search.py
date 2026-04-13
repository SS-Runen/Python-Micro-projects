"""
Bounded beam search over purchase prefixes for farm builds. See OPTIMIZATION_CRITERIA.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .config import FarmMode
from .data_loader import GameDataBundle
from .models import ChampionProfile
from .simulator import PurchasePolicy, SimResult, SimulationState, acquire_goal, simulate
from .greedy_farm_build import (
    BeamFarmMetadata,
    GreedyFarmMetadata,
    make_forced_prefix_then_greedy_hook,
    make_greedy_hook,
    ranked_marginal_acquisitions,
)

MarginalObjective = Literal["dps_per_gold", "horizon_greedy_roi"]


def _empty_state(data: GameDataBundle) -> SimulationState:
    return SimulationState(
        time_seconds=0.0,
        gold=float(data.rules.start_gold),
        inventory=[],
        total_xp=0.0,
        level=1,
        buy_queue=[],
        total_gold_spent_on_items=0.0,
        blocked_purchase_ids=set(),
    )


def state_after_prefix(data: GameDataBundle, items: dict, prefix: tuple[str, ...]) -> SimulationState | None:
    st = _empty_state(data)
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
) -> list[tuple[str, float, float, float]]:
    """Rank next purchases by Δtotal_farm_gold vs baseline greedy (nested full sims)."""
    dps_ranked = ranked_marginal_acquisitions(state, profile, items, epsilon)
    cap = max(horizon_candidate_cap, 4)
    candidate_ids = [r[0] for r in dps_ranked[:cap]]
    if not candidate_ids:
        return []
    rows: list[tuple[str, float, float, float]] = []
    for iid in candidate_ids:
        order_i: list[str] = []
        hook_f = make_forced_prefix_then_greedy_hook(
            profile, items, defer_purchases_until, epsilon, (iid,), order_sink=order_i
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
) -> list[tuple[str, float, float, float]]:
    st = state_after_prefix(data, items, prefix)
    if st is None:
        return []
    if prefix:
        return ranked_marginal_acquisitions(st, profile, items, epsilon)
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
        )
    return ranked_marginal_acquisitions(st, profile, items, epsilon)


@dataclass
class FarmBuildSearch:
    """
    Beam search over purchase prefixes; scores leaves with full-horizon ``total_farm_gold``.
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

    def run(self) -> tuple[tuple[str, ...], float, SimResult, BeamFarmMetadata | GreedyFarmMetadata]:
        profile = self.data.champions[self.champion_id]
        items = self.data.items
        d = max(1, self.beam_depth)
        w = max(1, self.beam_width)

        order_g: list[str] = []
        hook_g = make_greedy_hook(
            profile, items, self.defer_purchases_until, self.epsilon, order_sink=order_g
        )
        res_g = simulate(
            self.data,
            self.champion_id,
            self.farm_mode,
            PurchasePolicy(buy_order=()),
            eta_lane=self.eta_lane,
            t_max=self.t_max,
            defer_purchases_until=self.defer_purchases_until,
            purchase_hook=hook_g,
        )
        leaves_evaluated = 1
        best_val = res_g.total_farm_gold
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
                    )
                    res_i = simulate(
                        self.data,
                        self.champion_id,
                        self.farm_mode,
                        PurchasePolicy(buy_order=()),
                        eta_lane=self.eta_lane,
                        t_max=self.t_max,
                        defer_purchases_until=self.defer_purchases_until,
                        purchase_hook=hook_f,
                    )
                    leaves_evaluated += 1
                    fv = res_i.total_farm_gold
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
    "MarginalObjective",
    "state_after_prefix",
]
