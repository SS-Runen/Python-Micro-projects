"""
Layered heuristics for wave-clear / farm build search over the full Data Dragon catalog.

**Ordering (reject / rank before greedy or beam search):**

1. **Hard rejects** — Data Dragon ``tags`` (support, world-atlas gold items, consumables, trinkets,
   vision), plus **lane mode**: drop modern **jungle pet starters** (tag set exactly ``Jungle``) so
   laners do not shop jungle companions. Does **not** remove recipe components globally; see
   :func:`downward_recipe_closure`.
2. **Optional require-tags** — role-shaped catalog (e.g. ``SpellDamage``, ``Damage``); callers pass
   through :func:`~LoLPerfmon.sim.item_tag_filters.filter_items_by_tags`.
3. **Kit-aligned value proxy** — :func:`modeled_dps_uplift_per_gold` uses champion level,
   :func:`~LoLPerfmon.sim.stats.total_stats` with a **single-item** inventory, and
   :func:`~LoLPerfmon.sim.clear.effective_dps`. Ranks items by **modeled ΔDPS per gold** for the
   champion kit (not raw tag overlap). Used for diagnostics and optional top-K narrowing.

Recipe **closure**: Any kept purchasable item must still have its ``from_ids`` components present in
the dict passed to :func:`~LoLPerfmon.sim.simulator.simulate`; :func:`downward_recipe_closure`
adds missing components from the full bundle so ``acquire_goal`` can craft.
"""

from __future__ import annotations

from collections.abc import Mapping

from .clear import effective_dps
from .config import FarmMode
from .item_tag_filters import filter_items_by_tags
from .jungle_items import is_jungle_pet_companion_starter
from .models import ChampionProfile, ItemDef
from .stats import total_stats

DEFAULT_WAVECLEAR_EXCLUDE_TAGS: frozenset[str] = frozenset(
    {"Support", "GoldPer", "Consumable", "Trinket", "Vision"}
)


def downward_recipe_closure(
    seed_ids: set[str],
    full_items: Mapping[str, ItemDef],
) -> dict[str, ItemDef]:
    """
    Include every ``from_ids`` component reachable from ``seed_ids`` (transitive), so the shop
    dict remains recipe-complete for crafting parents in ``seed_ids``.
    """
    out: dict[str, ItemDef] = {}
    stack = [i for i in seed_ids if i in full_items]
    seen: set[str] = set()
    while stack:
        iid = stack.pop()
        if iid in seen:
            continue
        seen.add(iid)
        it = full_items[iid]
        out[iid] = it
        for fid in it.from_ids:
            if fid in full_items and fid not in seen:
                stack.append(fid)
    return out


def filter_waveclear_item_catalog(
    full_items: Mapping[str, ItemDef],
    farm_mode: FarmMode,
    *,
    exclude_tags: frozenset[str] | None = None,
    require_tags: frozenset[str] | None = None,
) -> dict[str, ItemDef]:
    """
    Apply default wave-clear excludes (or ``exclude_tags``), optional ``require_tags``, lane pet
    strip, then **downward recipe closure** from the surviving seeds.

    **Layer 1:** tag intersection exclude + optional require (see :mod:`item_tag_filters`).
    **Lane:** remove jungle pet starters (:func:`~LoLPerfmon.sim.jungle_items.is_jungle_pet_companion_starter`).
    **Closure:** all ``from_ids`` chains from full bundle so components exist for recipes.
    """
    ex = DEFAULT_WAVECLEAR_EXCLUDE_TAGS if exclude_tags is None else exclude_tags
    raw = filter_items_by_tags(dict(full_items), exclude_tags=ex, require_tags=require_tags)
    if farm_mode == FarmMode.LANE:
        raw = {iid: it for iid, it in raw.items() if not is_jungle_pet_companion_starter(it)}
    seeds = set(raw.keys())
    return downward_recipe_closure(seeds, full_items)


def modeled_dps_uplift_per_gold(
    profile: ChampionProfile,
    item_id: str,
    items_by_id: Mapping[str, ItemDef],
    *,
    level: int = 11,
    epsilon: float = 1e-9,
) -> float:
    """
    Static proxy: (effective_dps with only ``item_id`` in inventory − base dps) / ``total_cost``.

    Aligns heuristic ranking with the same :func:`~LoLPerfmon.sim.clear.effective_dps` path used
    in simulation (stats → DPS). Does not replace a full forward sim (no throughput cap, no income).
    """
    if item_id not in items_by_id:
        return 0.0
    it = items_by_id[item_id]
    st0 = total_stats(profile, level, (), items_by_id)
    d0 = effective_dps(profile, level, st0)
    st1 = total_stats(profile, level, (item_id,), items_by_id)
    d1 = effective_dps(profile, level, st1)
    return (d1 - d0) / max(it.total_cost, epsilon)


def modeled_delta_effective_dps(
    profile: ChampionProfile,
    item_id: str,
    items_by_id: Mapping[str, ItemDef],
    *,
    level: int = 11,
) -> float:
    """
    Static proxy for “does this item move modeled clear DPS at all?” — Δ[`effective_dps`](clear.py)
    with a **single copy** in inventory vs empty, at ``level``.
    """
    st0 = total_stats(profile, level, (), items_by_id)
    d0 = effective_dps(profile, level, st0)
    st1 = total_stats(profile, level, (item_id,), items_by_id)
    d1 = effective_dps(profile, level, st1)
    return d1 - d0


def upward_recipe_closure_within_catalog(
    seed_ids: set[str],
    items_by_id: Mapping[str, ItemDef],
) -> set[str]:
    """
    Every item id in ``items_by_id`` that lists at least one id in the current target set in
    ``into_ids`` (Data Dragon “builds into”), transitively — i.e. prerequisites on paths toward
    ``seed_ids``. Stays inside ``items_by_id`` keys only.
    """
    targets: set[str] = set(seed_ids)
    out: set[str] = set(seed_ids)
    changed = True
    while changed:
        changed = False
        for iid, it in items_by_id.items():
            if iid in out:
                continue
            if any(ch in targets for ch in it.into_ids):
                out.add(iid)
                targets.add(iid)
                changed = True
    return out


def meaningful_waveclear_exploration_catalog(
    full_items: Mapping[str, ItemDef],
    farm_mode: FarmMode,
    profile: ChampionProfile,
    *,
    exclude_tags: frozenset[str] | None = None,
    require_tags: frozenset[str] | None = None,
    reference_level: int = 11,
    dps_delta_epsilon: float = 1e-4,
) -> dict[str, ItemDef]:
    """
    Wave-clear catalog (tag + lane pet rules + downward closure), then drop items with **no**
    modeled Δ[`effective_dps`](clear.py) at ``reference_level``, add **upward** ``into_ids``
    prerequisites toward surviving seeds, then **downward** ``from_ids`` closure from the merged
    set so recipes stay valid for :func:`~LoLPerfmon.sim.simulator.acquire_goal`.

    If every item fails the DPS gate, returns the unfiltered wave-clear dict (fallback).
    """
    base = filter_waveclear_item_catalog(
        full_items,
        farm_mode,
        exclude_tags=exclude_tags,
        require_tags=require_tags,
    )
    seeds = {
        iid
        for iid in base
        if modeled_delta_effective_dps(profile, iid, full_items, level=reference_level) > dps_delta_epsilon
    }
    if not seeds:
        return base
    up = upward_recipe_closure_within_catalog(seeds, base)
    merged = seeds | up
    return downward_recipe_closure(merged, full_items)


def exploration_path_value_by_item(
    profile: ChampionProfile,
    items_by_id: Mapping[str, ItemDef],
    *,
    reference_level: int = 11,
    ideal_target_top_k: int = 16,
    ideal_path_boost: float = 0.25,
) -> dict[str, float]:
    """
    Static path value for purchase ranking: for each item id, take the maximum
    :func:`modeled_dps_uplift_per_gold` over itself and all items reachable following Data Dragon
    ``into_ids`` (finished upgrades). Optionally scale up that max when the subtree can reach one
    of the top-``ideal_target_top_k`` items by :func:`modeled_delta_effective_dps` at
    ``reference_level`` (proxy “high clear” ideal targets for the kit).

    Bounded ``O(|items| + edges)`` with memoization; cycles in ``into_ids`` are guarded.
    """
    if not items_by_id:
        return {}
    k = max(1, min(ideal_target_top_k, len(items_by_id)))
    ranked = sorted(
        (
            (iid, modeled_delta_effective_dps(profile, iid, items_by_id, level=reference_level))
            for iid in items_by_id
        ),
        key=lambda t: (-t[1], t[0]),
    )
    ideal_set = frozenset(t[0] for t in ranked[:k])
    memo_raw: dict[str, float] = {}
    memo_reach: dict[str, bool] = {}
    visiting: set[str] = set()

    def dfs(iid: str) -> tuple[float, bool]:
        if iid in memo_raw:
            return memo_raw[iid], memo_reach[iid]
        if iid not in items_by_id:
            return 0.0, False
        if iid in visiting:
            u = modeled_dps_uplift_per_gold(profile, iid, items_by_id, level=reference_level)
            return u, iid in ideal_set
        visiting.add(iid)
        u = modeled_dps_uplift_per_gold(profile, iid, items_by_id, level=reference_level)
        raw_max = u
        reach = iid in ideal_set
        for c in items_by_id[iid].into_ids:
            if c not in items_by_id:
                continue
            rc, rr = dfs(c)
            raw_max = max(raw_max, rc)
            reach = reach or rr
        visiting.remove(iid)
        memo_raw[iid] = raw_max
        memo_reach[iid] = reach
        return raw_max, reach

    for root in items_by_id:
        dfs(root)
    mult = 1.0 + ideal_path_boost
    return {
        iid: memo_raw[iid] * (mult if memo_reach[iid] else 1.0)
        for iid in items_by_id
        if iid in memo_raw
    }


def rank_item_ids_by_dps_uplift_per_gold(
    profile: ChampionProfile,
    items_by_id: Mapping[str, ItemDef],
    *,
    level: int = 11,
) -> list[tuple[str, float]]:
    """
    Sort all item ids in ``items_by_id`` by :func:`modeled_dps_uplift_per_gold` descending.
    For diagnostics and optional candidate narrowing; bounded linear work over ``len(items)``.
    """
    rows: list[tuple[str, float]] = []
    for iid in sorted(items_by_id.keys()):
        rows.append((iid, modeled_dps_uplift_per_gold(profile, iid, items_by_id, level=level)))
    rows.sort(key=lambda t: (-t[1], t[0]))
    return rows


__all__ = [
    "DEFAULT_WAVECLEAR_EXCLUDE_TAGS",
    "downward_recipe_closure",
    "exploration_path_value_by_item",
    "filter_waveclear_item_catalog",
    "meaningful_waveclear_exploration_catalog",
    "modeled_delta_effective_dps",
    "modeled_dps_uplift_per_gold",
    "rank_item_ids_by_dps_uplift_per_gold",
    "upward_recipe_closure_within_catalog",
]
