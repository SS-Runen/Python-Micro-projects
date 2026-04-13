"""
Lane/jungle simulation with recipe purchases. **Selling or swapping items is not modeled.**
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from .models import ItemDef

from .clear import (
    clear_time_seconds,
    effective_dps,
    jungle_cycle_seconds,
    throughput_ratio,
    wave_gold_if_full_clear,
)
from .config import FarmMode, GameConfig
from .data_loader import GameDataBundle
from .passive import passive_gold_in_interval
from .stats import total_stats
from .xp_level import level_from_total_xp, xp_for_minion_kill

# Summoner's Rift inventory (item slots only; trinket/ward not modeled).
MAX_INVENTORY_SLOTS = 6


def inventory_count(inventory: list[str], item_id: str) -> int:
    return sum(1 for x in inventory if x == item_id)


def _inventory_has_boots(inventory: list[str], items_by_id: dict) -> bool:
    for sid in inventory:
        oit = items_by_id.get(sid)
        if oit is not None and "Boots" in oit.tags:
            return True
    return False


def _boots_blocks_purchase(inventory: list[str], target_id: str, items_by_id: dict) -> bool:
    it = items_by_id.get(target_id)
    if it is None or "Boots" not in it.tags:
        return False
    return _inventory_has_boots(inventory, items_by_id)


def _release_blocks_for_removed_items(state: "SimulationState", removed_ids: list[str]) -> None:
    for rid in removed_ids:
        state.blocked_purchase_ids.discard(rid)


def _register_acquisition_blocks(state: "SimulationState", target_id: str, it: ItemDef) -> None:
    if it.max_inventory_copies <= 1:
        state.blocked_purchase_ids.add(target_id)


def config_from_rules(data: GameDataBundle) -> GameConfig:
    r = data.rules
    return GameConfig(
        start_gold=r.start_gold,
        passive_gold_per_10_seconds=r.passive_gold_per_10_seconds,
        passive_gold_start_seconds=r.passive_gold_start_seconds,
        patch_version=r.patch_version,
    )


@dataclass(frozen=True)
class PurchasePolicy:
    buy_order: tuple[str, ...]


@dataclass
class SimulationState:
    time_seconds: float
    gold: float
    inventory: list[str]
    total_xp: float
    level: int
    buy_queue: list[str]
    total_gold_spent_on_items: float = 0.0
    #: Item ids that must not be purchased again this run (single-copy epics/legendaries; see :func:`_register_acquisition_blocks`).
    blocked_purchase_ids: set[str] = field(default_factory=set)


@dataclass
class SimResult:
    """
    Economic fields:

    - ``total_farm_gold`` — sum of **discrete** farm ticks in this model (not a continuous
      last-hit integral).

      **Lane** (``FarmMode.LANE``): per arriving wave,
      ``gold_gain = wave_gold_if_full_clear × throughput_ratio(clear_time, wave_interval) × eta_lane``,
      where ``clear_time = wave_hp_budget / effective_dps`` (see ``clear.py``). Throughput
      caps at a full wave; higher DPS raises income until that cap.

      **Jungle**: per route cycle,
      ``gold_gain = jungle_base_route_gold × min(1, base_cycle_seconds / jungle_cycle_seconds)``,
      with ``jungle_cycle_seconds`` scaling inversely with ``effective_dps``.

      **Preferred default for build optimization** under this simulator (not a claim of
      real-client optimality).

    - ``total_passive_gold`` — passive income (does not depend on items in this model).
    - ``total_gold_spent_on_items`` — all gold paid to the shop (components + crafts + full buys).
    - ``final_gold`` — wallet after income and purchases (``starting_gold`` + farm + passive - spent).
    - ``net_wealth_delta`` — ``final_gold - starting_gold`` (= farm + passive - spent).
    """

    final_gold: float
    final_level: float
    final_inventory: tuple[str, ...]
    timeline: list[tuple[float, float, int]]
    total_farm_gold: float
    total_passive_gold: float
    total_gold_spent_on_items: float
    starting_gold: float
    net_wealth_delta: float


def default_build_optimizer_score(res: SimResult) -> float:
    """
    Maximize ``total_farm_gold`` from :class:`SimResult` — the simulator’s lane/jungle farm
    sums described there. Does **not** maximize residual ``final_gold`` (wallet).
    """
    return res.total_farm_gold


def _cs_cumulative_by_wave(data: GameDataBundle) -> dict[int, int]:
    return data.cumulative_cs_by_wave_index()


def _delta_cs(wave_index: int, cum: dict[int, int]) -> int:
    if wave_index not in cum:
        return 0
    cur = cum[wave_index]
    if wave_index <= 0:
        return cur
    prev = cum.get(wave_index - 1, 0)
    return cur - prev


def _acquire_goal(state: SimulationState, target_id: str, items_by_id: dict) -> bool:
    """
    Acquire one copy of ``target_id`` using Data Dragon-style rules:
    - Leaf (no ``from_ids``): pay ``total_cost``, add item.
    - Composite: if inventory has **exact** recipe multiset, pay recipe fee
      (``total - sum(components)``), consume components, add item.
      If inventory has **some but not all** recipe pieces, refuse (buy components via earlier goals).
    - If inventory has **none** of the recipe pieces, allow **full sticker** purchase for ``total_cost``.

    At most :data:`MAX_INVENTORY_SLOTS` items after the operation. Combining consumes
    components and frees slots before the finished item occupies one slot.

    If the inventory already holds ``max_inventory_copies`` of ``target_id``, acquisition fails.

    Single-copy items already purchased are listed in ``state.blocked_purchase_ids``. At most one
    **Boots** item may be held (see ``ItemDef.tags``).
    """
    it = items_by_id.get(target_id)
    if not it:
        return False
    inv = state.inventory
    if target_id in state.blocked_purchase_ids:
        return False
    if _boots_blocks_purchase(inv, target_id, items_by_id):
        return False
    if inventory_count(inv, target_id) >= it.max_inventory_copies:
        return False
    if not it.from_ids:
        if len(inv) >= MAX_INVENTORY_SLOTS:
            return False
        if state.gold + 1e-9 < it.total_cost:
            return False
        paid = it.total_cost
        state.gold -= paid
        state.total_gold_spent_on_items += paid
        inv.append(target_id)
        _register_acquisition_blocks(state, target_id, it)
        return True

    need = Counter(it.from_ids)
    have = Counter(inv)
    matched = Counter()
    for k in need:
        if k not in items_by_id:
            return False
        matched[k] = min(need[k], have[k])
    matched_sum = sum(matched.values())
    if matched_sum > 0 and matched != need:
        return False
    if matched == need:
        comp_sum = sum(items_by_id[k].total_cost * need[k] for k in need)
        craft_cost = max(0.0, it.total_cost - comp_sum)
        remove_cnt = sum(need.values())
        new_len = len(inv) - remove_cnt + 1
        if new_len > MAX_INVENTORY_SLOTS:
            return False
        if state.gold + 1e-9 < craft_cost:
            return False
        removed: list[str] = []
        for k, n in need.items():
            for _ in range(n):
                inv.remove(k)
                removed.append(k)
        state.gold -= craft_cost
        state.total_gold_spent_on_items += craft_cost
        _release_blocks_for_removed_items(state, removed)
        inv.append(target_id)
        _register_acquisition_blocks(state, target_id, it)
        return True
    if len(inv) >= MAX_INVENTORY_SLOTS:
        return False
    if state.gold + 1e-9 < it.total_cost:
        return False
    paid = it.total_cost
    state.gold -= paid
    state.total_gold_spent_on_items += paid
    inv.append(target_id)
    _register_acquisition_blocks(state, target_id, it)
    return True


def acquire_goal(state: SimulationState, target_id: str, items_by_id: dict) -> bool:
    """
    Public wrapper for :func:`_acquire_goal` — recipe-valid single-item acquisition
    (used by greedy / beam farm search).
    """
    return _acquire_goal(state, target_id, items_by_id)


def _apply_purchases(state: SimulationState, items_by_id: dict, defer_purchases_until: float | None) -> None:
    changed = True
    while changed:
        changed = False
        if not state.buy_queue:
            break
        if defer_purchases_until is not None and state.time_seconds + 1e-9 < defer_purchases_until:
            break
        next_id = state.buy_queue[0]
        if next_id not in items_by_id:
            state.buy_queue.pop(0)
            changed = True
            continue
        nit = items_by_id.get(next_id)
        if next_id in state.blocked_purchase_ids:
            state.buy_queue.pop(0)
            changed = True
            continue
        if nit is not None and inventory_count(state.inventory, next_id) >= nit.max_inventory_copies:
            state.buy_queue.pop(0)
            changed = True
            continue
        if _acquire_goal(state, next_id, items_by_id):
            state.buy_queue.pop(0)
            changed = True


def _xp_for_wave_fraction(wave, level: int, fraction: float, rules) -> float:
    f = max(0.0, min(1.0, fraction))
    xm = xp_for_minion_kill("melee", level, rules)
    xc = xp_for_minion_kill("caster", level, rules)
    xs = xp_for_minion_kill("siege", level, rules)
    return f * (wave.melee * xm + wave.caster * xc + wave.siege * xs)


def _purchase_round(
    state: SimulationState,
    items_by_id: dict,
    defer_purchases_until: float | None,
    purchase_hook: Callable[[SimulationState], None] | None,
) -> None:
    if purchase_hook is not None:
        purchase_hook(state)
    else:
        _apply_purchases(state, items_by_id, defer_purchases_until)


def simulate(
    data: GameDataBundle,
    champion_id: str,
    farm_mode: FarmMode,
    policy: PurchasePolicy,
    eta_lane: float = 1.0,
    t_max: float | None = None,
    on_wave: Callable[[SimulationState, float, int], None] | None = None,
    defer_purchases_until: float | None = None,
    purchase_hook: Callable[[SimulationState], None] | None = None,
    lane_purchase_hook: Callable[[SimulationState], None] | None = None,
) -> SimResult:
    """
    If ``purchase_hook`` or ``lane_purchase_hook`` is set, it runs at each purchase point
    (lane waves or jungle cycles) instead of draining ``policy.buy_order`` via
    :func:`_apply_purchases`. Use for greedy or custom shop policies; leave
    ``policy.buy_order`` empty when the hook owns buys. ``lane_purchase_hook`` is a
    deprecated alias for ``purchase_hook``.
    """
    if champion_id not in data.champions:
        raise KeyError(champion_id)
    hook = purchase_hook if purchase_hook is not None else lane_purchase_hook
    profile = data.champions[champion_id]
    items = data.items
    rules = data.rules
    cfg = config_from_rules(data)
    t_end = t_max if t_max is not None else cfg.t_max_seconds
    starting_gold = float(rules.start_gold)

    state = SimulationState(
        time_seconds=0.0,
        gold=starting_gold,
        inventory=[],
        total_xp=0.0,
        level=1,
        buy_queue=list(policy.buy_order),
        total_gold_spent_on_items=0.0,
        blocked_purchase_ids=set(),
    )
    cum = _cs_cumulative_by_wave(data)
    max_wave_index = max(cum.keys()) if cum else 0
    timeline: list[tuple[float, float, int]] = [(0.0, state.gold, state.level)]
    total_farm = 0.0
    total_passive = 0.0
    t_prev = 0.0

    if farm_mode == FarmMode.LANE:
        k = 0
        while True:
            t_wave = rules.first_wave_spawn_seconds + k * rules.wave_interval_seconds
            if t_wave > t_end:
                break
            if k > max_wave_index:
                break
            pg = passive_gold_in_interval(t_prev, t_wave, cfg)
            state.gold += pg
            total_passive += pg
            state.time_seconds = t_wave
            _purchase_round(state, items, defer_purchases_until, hook)
            wave = data.wave_at_index(k)
            if wave is None:
                k += 1
                t_prev = t_wave
                continue
            stats = total_stats(profile, state.level, tuple(state.inventory), items)
            game_minute = t_wave / 60.0
            dps = effective_dps(profile, state.level, stats)
            ct = clear_time_seconds(wave, game_minute, data, dps)
            thr = throughput_ratio(ct, rules.wave_interval_seconds) * eta_lane
            gold_full = wave_gold_if_full_clear(wave, game_minute, data)
            gold_gain = gold_full * thr
            xp_gain = _xp_for_wave_fraction(wave, state.level, thr, rules)
            state.gold += gold_gain
            total_farm += gold_gain
            state.total_xp += xp_gain
            state.level = level_from_total_xp(state.total_xp, rules)
            _purchase_round(state, items, defer_purchases_until, hook)
            timeline.append((state.time_seconds, state.gold, state.level))
            if on_wave:
                on_wave(state, t_wave, k)
            t_prev = t_wave
            k += 1
    else:
        t_next = rules.jungle_base_cycle_seconds
        while t_next <= t_end:
            pg = passive_gold_in_interval(t_prev, t_next, cfg)
            state.gold += pg
            total_passive += pg
            state.time_seconds = t_next
            _purchase_round(state, items, defer_purchases_until, hook)
            stats = total_stats(profile, state.level, tuple(state.inventory), items)
            cycle = jungle_cycle_seconds(profile, state.level, stats, data)
            eff = min(1.0, rules.jungle_base_cycle_seconds / max(cycle, 1e-9))
            gold_gain = rules.jungle_base_route_gold * eff
            xp_gain = rules.jungle_base_route_xp * eff
            state.gold += gold_gain
            total_farm += gold_gain
            state.total_xp += xp_gain
            state.level = level_from_total_xp(state.total_xp, rules)
            _purchase_round(state, items, defer_purchases_until, hook)
            timeline.append((state.time_seconds, state.gold, state.level))
            if on_wave:
                on_wave(state, t_next, -1)
            t_prev = t_next
            t_next += rules.jungle_base_cycle_seconds

    if t_prev < t_end:
        pg = passive_gold_in_interval(t_prev, t_end, cfg)
        state.gold += pg
        total_passive += pg
        state.time_seconds = t_end
        _purchase_round(state, items, defer_purchases_until, hook)
        timeline.append((state.time_seconds, state.gold, state.level))

    net_delta = state.gold - starting_gold
    return SimResult(
        final_gold=state.gold,
        final_level=float(state.level),
        final_inventory=tuple(state.inventory),
        timeline=timeline,
        total_farm_gold=total_farm,
        total_passive_gold=total_passive,
        total_gold_spent_on_items=state.total_gold_spent_on_items,
        starting_gold=starting_gold,
        net_wealth_delta=net_delta,
    )
