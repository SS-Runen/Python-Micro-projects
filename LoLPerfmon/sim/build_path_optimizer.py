from __future__ import annotations

import itertools
from typing import Callable, Mapping

from .config import FarmMode
from .data_loader import GameDataBundle
from .models import ItemDef
from .simulator import PurchasePolicy, SimResult, default_build_optimizer_score, simulate

# Exhaustive interleaving is factorial-like; keep default small for CI.
_DEFAULT_MAX_INTERLEAVE_STEPS = 12


def acquisition_postorder_for_item(item_id: str, items: Mapping[str, ItemDef], stack: set[str] | None = None) -> tuple[str, ...]:
    """
    One valid purchase order for a single item: recursively buy/craft components left-to-right
    in Data Dragon ``from`` order, then acquire the parent (craft or full buy).
    """
    if stack is None:
        stack = set()
    if item_id in stack:
        raise ValueError(f"recipe cycle involving {item_id}")
    it = items[item_id]
    stack.add(item_id)
    if not it.from_ids:
        stack.remove(item_id)
        return (item_id,)
    seq: tuple[str, ...] = ()
    for comp in it.from_ids:
        seq += acquisition_postorder_for_item(comp, items, stack)
    stack.remove(item_id)
    return seq + (item_id,)


def _all_interleavings(seqs: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    total_len = sum(len(s) for s in seqs)
    if total_len == 0:
        return [()]
    out: list[tuple[str, ...]] = []

    def dfs(path: list[str], idx: list[int]) -> None:
        if len(path) == total_len:
            out.append(tuple(path))
            return
        for i in range(len(seqs)):
            j = idx[i]
            if j < len(seqs[i]):
                idx2 = list(idx)
                idx2[i] = j + 1
                dfs(path + [seqs[i][j]], idx2)

    dfs([], [0] * len(seqs))
    return out


def _candidate_goal_orders(seqs: list[tuple[str, ...]], max_interleave_steps: int) -> list[tuple[str, ...]]:
    total_len = sum(len(s) for s in seqs)
    if total_len <= max_interleave_steps:
        return _all_interleavings(seqs)
    out: list[tuple[str, ...]] = []
    for perm in itertools.permutations(range(len(seqs))):
        t: tuple[str, ...] = ()
        for i in perm:
            t += seqs[i]
        out.append(t)
    return out


def optimal_interleaved_build(
    data: GameDataBundle,
    champion_id: str,
    farm_mode: FarmMode,
    root_item_ids: tuple[str, ...],
    score: Callable[[SimResult], float] = default_build_optimizer_score,
    eta_lane: float = 1.0,
    t_max: float | None = None,
    max_interleave_steps: int = _DEFAULT_MAX_INTERLEAVE_STEPS,
) -> tuple[tuple[str, ...], float, SimResult]:
    """
    Search over purchase **goal** orders for one or more **root** items (e.g. mythic + Doran's).

    For each root, expand to a post-order acquisition sequence using :func:`acquisition_postorder_for_item`.
    If the combined length is at most ``max_interleave_steps``, try **every** merge order that preserves
    the relative order inside each root's sequence; otherwise try only **block permutations**
    (concatenate whole sequences in every order of roots).

    This matches the recipe-aware simulator: goals are satisfied in order; crafts trigger when the
    inventory holds the full ``from`` multiset.

    For **clear-count** optimization, pass ``score`` as a callable that uses
    :func:`~LoLPerfmon.sim.simulator.default_clear_count_score` with the same ``farm_mode``
    argument (see :class:`~LoLPerfmon.sim.simulator.SimResult` ``total_lane_minions_cleared`` /
    ``total_jungle_monsters_cleared``) instead of :func:`~LoLPerfmon.sim.simulator.default_build_optimizer_score`.
    """
    items = data.items
    for rid in root_item_ids:
        if rid not in items:
            raise KeyError(rid)
    seqs = [acquisition_postorder_for_item(rid, items) for rid in root_item_ids]
    candidates = _candidate_goal_orders(seqs, max_interleave_steps)
    best_order: tuple[str, ...] = ()
    best_val = float("-inf")
    best_res: SimResult | None = None
    for goals in candidates:
        pol = PurchasePolicy(buy_order=tuple(goals))
        res = simulate(data, champion_id, farm_mode, pol, eta_lane=eta_lane, t_max=t_max)
        v = score(res)
        if v > best_val:
            best_val = v
            best_order = tuple(goals)
            best_res = res
    assert best_res is not None
    return best_order, best_val, best_res


def optimal_build_for_item_order_roots(
    data: GameDataBundle,
    champion_id: str,
    farm_mode: FarmMode,
    root_item_ids: tuple[str, ...],
    score: Callable[[SimResult], float] = default_build_optimizer_score,
    eta_lane: float = 1.0,
    t_max: float | None = None,
) -> tuple[tuple[str, ...], float, SimResult]:
    """
    Compare every **order of root items** (e.g. mythic vs boots), expanding each root with
    :func:`acquisition_postorder_for_item`, concatenating whole blocks in permuted order.
    Does **not** interleave component steps across roots; use :func:`optimal_interleaved_build` for that.

    Pass ``score`` as for :func:`optimal_interleaved_build` when optimizing minion/monster clears.
    """
    items = data.items
    per_root = tuple(acquisition_postorder_for_item(r, items) for r in root_item_ids)
    best_order: tuple[str, ...] = ()
    best_val = float("-inf")
    best_res: SimResult | None = None
    for perm in itertools.permutations(range(len(root_item_ids))):
        goals: tuple[str, ...] = tuple()
        for i in perm:
            goals += per_root[i]
        pol = PurchasePolicy(buy_order=goals)
        res = simulate(data, champion_id, farm_mode, pol, eta_lane=eta_lane, t_max=t_max)
        v = score(res)
        if v > best_val:
            best_val = v
            best_order = goals
            best_res = res
    assert best_res is not None
    return best_order, best_val, best_res


def acquisition_sequence_for_finished_roots(
    items: Mapping[str, ItemDef], *root_item_ids: str
) -> tuple[str, ...]:
    """
    Concatenate :func:`acquisition_postorder_for_item` for each root in order.

    Use when you want a single deterministic goal queue (components → parent per root)
    without searching interleavings. For ordering **between** roots, prefer
    :func:`optimal_interleaved_build` or :func:`optimal_build_for_item_order_roots`.
    """
    seq: tuple[str, ...] = ()
    for rid in root_item_ids:
        if rid not in items:
            raise KeyError(rid)
        seq += acquisition_postorder_for_item(rid, items)
    return seq


__all__ = [
    "acquisition_postorder_for_item",
    "acquisition_sequence_for_finished_roots",
    "optimal_interleaved_build",
    "optimal_build_for_item_order_roots",
]
