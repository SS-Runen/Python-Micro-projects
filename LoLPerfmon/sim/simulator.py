"""
Lane/jungle simulation with recipe purchases. **Selling** uses a deterministic rule: **50%**
of ``ItemDef.total_cost`` credited (see :mod:`sell_economy`, assumption A9).

- :func:`sell_item_once` — any inventory item.
- :func:`sell_jungle_companion_once` — jungle-tagged companion only (same refund).
- :func:`sell_lane_starter_once` — Doran's / Dark Seal–style starters only; greedy hooks may
  call these when ``allow_lane_starter_sell`` is True — see :func:`try_acquire_with_lane_starter_sells`.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from .models import ItemDef

from .clear import (
    clear_time_seconds,
    effective_dps,
    jungle_cycle_seconds,
    lane_available_seconds,
    throughput_ratio,
    wave_gold_if_full_clear,
)
from .config import FarmMode, GameConfig
from .data_loader import GameDataBundle, wave_minion_count
from .passive import passive_gold_in_interval
from .stats import total_stats
from .wave_schedule import wave_composition_at_index
from .xp_level import level_from_total_xp, xp_for_minion_kill
from .jungle_items import (
    JUNGLE_COMPANION_SELL_REFUND_FRACTION,
    is_jungle_companion_item,
    resolve_jungle_starter_item_id,
)
from .lane_items import is_resellable_lane_starter
from .sell_economy import shop_sell_refund_gold

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
    #: Credits from :func:`sell_item_once` / companion sell (not farm or passive ticks).
    total_shop_sell_gold: float = 0.0
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
    - ``total_shop_sell_gold`` — gold credited from shop sells (lane starters, items, jungle pet sell).
    - ``total_gold_spent_on_items`` — all gold paid to the shop (components + crafts + full buys).
    - ``final_gold`` — wallet after income and purchases
      (``starting_gold + total_farm_gold + total_passive_gold + total_shop_sell_gold - total_gold_spent_on_items``).
    - ``net_wealth_delta`` — ``final_gold - starting_gold`` (includes sells; see :func:`gold_flow_reconciliation_error`).
    - ``ended_by_early_stop`` — True when ``simulate(..., early_stop=...)`` returned early.

    **Throughput aggregates (lane/jungle):** sums of per-tick **throughput** scalars—useful
    as a deterministic proxy for “how much wave/camp income was unlocked” (not raw minion counts).

    - ``total_lane_throughput_units`` — lane only: sum of ``throughput_ratio × eta_lane`` per wave.
    - ``total_jungle_route_eff_units`` — jungle only: sum of per-cycle route efficiency ``eff``.

    **Clear counts (interpretable kill proxies, not last-hit RNG):**

    - ``total_lane_minions_cleared`` — lane only: sum per wave of ``throughput_ratio × eta_lane × minion_count`` (same ``thr`` as gold; count is uniform across melee/caster/siege).
    - ``total_jungle_monsters_cleared`` — jungle only: sum per cycle of ``eff × jungle_monsters_per_route``.

    **Split farm income (mutually exclusive by ``FarmMode``):**

    - ``total_lane_minion_farm_gold`` — lane only: sum of per-wave lane ``gold_gain`` (minion wave income proxy). Zero in ``FarmMode.JUNGLE``.
    - ``total_jungle_monster_farm_gold`` — jungle only: sum of per-cycle ``gold_gain`` from abstract routes (monster/camp farm proxy). Zero in ``FarmMode.LANE``.

    ``total_farm_gold`` remains ``total_lane_minion_farm_gold + total_jungle_monster_farm_gold`` (one term zero per run). Do **not** add lane and jungle farm gold into one optimization objective across modes.
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
    total_shop_sell_gold: float = 0.0
    ended_by_early_stop: bool = False
    total_lane_throughput_units: float = 0.0
    total_jungle_route_eff_units: float = 0.0
    total_lane_minions_cleared: float = 0.0
    total_jungle_monsters_cleared: float = 0.0
    total_lane_minion_farm_gold: float = 0.0
    total_jungle_monster_farm_gold: float = 0.0


def default_build_optimizer_score(res: SimResult) -> float:
    """
    Maximize ``total_farm_gold`` from :class:`SimResult` — the simulator’s lane/jungle farm
    sums described there. Does **not** maximize residual ``final_gold`` (wallet).
    """
    return res.total_farm_gold


def primary_farm_gold_for_mode(res: SimResult, farm_mode: FarmMode) -> float:
    """
    Farm ticks attributed to the active ``farm_mode`` only: lane minion proxy vs jungle route proxy.
    Equals :attr:`SimResult.total_farm_gold` for any single-mode run (the other bucket is zero).
    """
    if farm_mode == FarmMode.LANE:
        return res.total_lane_minion_farm_gold
    return res.total_jungle_monster_farm_gold


def gold_income_breakdown(res: SimResult) -> dict[str, float]:
    """
    Return named gold components for troubleshooting (all from :class:`SimResult`).

    Farm ticks are **lane or jungle** per ``simulate`` mode; there is no separate “last-hit” lane
    gold. Passive uses :mod:`passive` rules (SR default: linear rate after ``passive_gold_start_seconds``).
    """
    return {
        "starting_gold": res.starting_gold,
        "total_farm_gold": res.total_farm_gold,
        "total_lane_minion_farm_gold": res.total_lane_minion_farm_gold,
        "total_jungle_monster_farm_gold": res.total_jungle_monster_farm_gold,
        "total_passive_gold": res.total_passive_gold,
        "total_shop_sell_gold": res.total_shop_sell_gold,
        "total_gold_spent_on_items": res.total_gold_spent_on_items,
        "final_gold": res.final_gold,
        "net_wealth_delta": res.net_wealth_delta,
    }


def gold_flow_reconciliation_error(res: SimResult, epsilon: float = 1e-6) -> float:
    """
    Absolute error between ``final_gold`` and the book-keeping sum
    ``starting + farm + passive + sells - spent``. Should be ~0 for every :func:`simulate` run.
    """
    implied = (
        res.starting_gold
        + res.total_farm_gold
        + res.total_passive_gold
        + res.total_shop_sell_gold
        - res.total_gold_spent_on_items
    )
    return abs(implied - res.final_gold)


def default_clear_count_score(res: SimResult, farm_mode: FarmMode) -> float:
    """
    Maximize modeled minion or monster clears over the horizon (see :class:`SimResult` clear fields).
    Use when optimizing **clear volume**, not ``total_farm_gold`` (gold-weighted lane income).
    """
    if farm_mode == FarmMode.LANE:
        return res.total_lane_minions_cleared
    return res.total_jungle_monsters_cleared


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


def sell_item_once(
    state: SimulationState,
    item_id: str,
    items_by_id: dict[str, ItemDef],
) -> bool:
    """
    Remove one copy of ``item_id`` from the bag and credit :func:`~LoLPerfmon.sim.sell_economy.shop_sell_refund_gold`
    (50% of ``total_cost``).
    """
    it = items_by_id.get(item_id)
    if it is None or inventory_count(state.inventory, item_id) < 1:
        return False
    state.inventory.remove(item_id)
    refund = shop_sell_refund_gold(it)
    state.gold += refund
    state.total_shop_sell_gold += refund
    state.blocked_purchase_ids.discard(item_id)
    return True


def sell_jungle_companion_once(
    state: SimulationState,
    companion_id: str,
    items_by_id: dict[str, ItemDef],
    refund_fraction: float = JUNGLE_COMPANION_SELL_REFUND_FRACTION,
) -> bool:
    """Remove one jungle-tagged companion and credit ``refund_fraction * total_cost`` gold."""
    it = items_by_id.get(companion_id)
    if it is None or not is_jungle_companion_item(it):
        return False
    if inventory_count(state.inventory, companion_id) < 1:
        return False
    if math.isclose(refund_fraction, JUNGLE_COMPANION_SELL_REFUND_FRACTION):
        return sell_item_once(state, companion_id, items_by_id)
    state.inventory.remove(companion_id)
    credit = float(it.total_cost) * refund_fraction
    state.gold += credit
    state.total_shop_sell_gold += credit
    state.blocked_purchase_ids.discard(companion_id)
    return True


def sell_lane_starter_once(
    state: SimulationState,
    item_id: str,
    items_by_id: dict[str, ItemDef],
) -> bool:
    """Remove one resellable lane starter and credit the standard shop sell refund."""
    it = items_by_id.get(item_id)
    if it is None or not is_resellable_lane_starter(it):
        return False
    return sell_item_once(state, item_id, items_by_id)


def sell_one_lane_starter_lex_first(
    state: SimulationState,
    items_by_id: dict[str, ItemDef],
) -> bool:
    """Sell one resellable lane starter; deterministic order by sorted distinct item ids in the bag."""
    for iid in sorted(set(state.inventory)):
        it = items_by_id.get(iid)
        if it is not None and is_resellable_lane_starter(it):
            return sell_lane_starter_once(state, iid, items_by_id)
    return False


def try_acquire_with_lane_starter_sells(
    state: SimulationState,
    target_id: str,
    items_by_id: dict[str, ItemDef],
    *,
    max_sells: int = 24,
) -> bool:
    """
    Try :func:`acquire_goal`; if it fails, repeatedly sell lane starters (lex-first) until
    the purchase succeeds or nothing resellable remains.
    """
    if acquire_goal(state, target_id, items_by_id):
        return True
    for _ in range(max_sells):
        if not sell_one_lane_starter_lex_first(state, items_by_id):
            return acquire_goal(state, target_id, items_by_id)
        if acquire_goal(state, target_id, items_by_id):
            return True
    return acquire_goal(state, target_id, items_by_id)


def sell_one_non_lane_starter_item_lex_first(
    state: SimulationState,
    items_by_id: dict[str, ItemDef],
) -> bool:
    """Sell one non-lane-starter item (lexicographic distinct ids) to credit standard shop refund."""
    for iid in sorted(set(state.inventory)):
        it = items_by_id.get(iid)
        if it is None or is_resellable_lane_starter(it):
            continue
        return sell_item_once(state, iid, items_by_id)
    return False


def try_acquire_with_shop_sells(
    state: SimulationState,
    target_id: str,
    items_by_id: dict[str, ItemDef],
    *,
    max_sells: int = 24,
    allow_sell_non_starter_items: bool = False,
) -> bool:
    """
    Try :func:`acquire_goal`; if it fails, sell lane starters (lex-first), then optionally
    any other inventory items, until the purchase succeeds or ``max_sells`` operations pass.
    """
    if acquire_goal(state, target_id, items_by_id):
        return True
    for _ in range(max_sells):
        progressed = False
        if sell_one_lane_starter_lex_first(state, items_by_id):
            progressed = True
        elif allow_sell_non_starter_items and sell_one_non_lane_starter_item_lex_first(
            state, items_by_id
        ):
            progressed = True
        if not progressed:
            return acquire_goal(state, target_id, items_by_id)
        if acquire_goal(state, target_id, items_by_id):
            return True
    return acquire_goal(state, target_id, items_by_id)


def blocked_purchase_ids_from_inventory(inventory: list[str], items_by_id: dict[str, ItemDef]) -> set[str]:
    """
    Rebuild duplicate-purchase blocks from the current bag: same rule as
    :func:`_register_acquisition_blocks` after buying an item with ``max_inventory_copies <= 1``.
    Used for post-hoc snapshots (e.g. marginal upgrade checks) where the full simulation
    ``blocked_purchase_ids`` history is not serialized on :class:`SimResult`.
    """
    out: set[str] = set()
    for iid in inventory:
        it = items_by_id.get(iid)
        if it is not None and it.max_inventory_copies <= 1:
            out.add(iid)
    return out


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
    on_lane_clear_dps: Callable[[float, int, float], None] | None = None,
    on_jungle_clear_dps: Callable[[float, int, float], None] | None = None,
    jungle_starter_item_id: str | None = None,
    jungle_sell_at_seconds: float | None = None,
    jungle_sell_only_after_level_18: bool = False,
    early_stop: Callable[[SimulationState], bool] | None = None,
    extrapolate_lane_waves: bool | None = None,
) -> SimResult:
    """
    If ``purchase_hook`` or ``lane_purchase_hook`` is set, it runs at each purchase point
    (lane waves or jungle cycles) instead of draining ``policy.buy_order`` via
    :func:`_apply_purchases`. Use for greedy or custom shop policies; leave
    ``policy.buy_order`` empty when the hook owns buys. ``lane_purchase_hook`` is a
    deprecated alias for ``purchase_hook``.

    ``on_lane_clear_dps`` (lane only): called each wave with ``(t_wave_seconds, wave_index,
    effective_dps)`` after pre-wave purchases, using the same DPS that drives clear time.

    ``on_jungle_clear_dps`` (jungle only): called each cycle with ``(t_cycle_seconds,
    cycle_index, effective_dps)`` after pre-cycle purchases.

    **Jungle-only:** ``jungle_starter_item_id`` selects the companion (Data Dragon ``Jungle``
    tag); if ``None``, the lexicographically first companion in the bundle is used. The
    champion **must** start with that item (bought from starting gold). Optional sell:
    if ``jungle_sell_at_seconds`` is set, the first cycle at or after that time may sell
    the companion for ``JUNGLE_COMPANION_SELL_REFUND_FRACTION`` of ``total_cost`` (see
    :mod:`jungle_items`). If ``jungle_sell_only_after_level_18`` is True, sell is only
    attempted once ``level >= 18``.

    If ``early_stop`` is set, it is evaluated after purchase hooks at each lane wave or
    jungle cycle; when it returns True, the simulation ends immediately (no padding of
    passive gold to ``t_max``). :attr:`SimResult.ended_by_early_stop` is True in that case.

    **Time horizon:** pass ``t_max=float("inf")`` for no fixed end time; this **requires**
    ``early_stop`` (otherwise the sim would not terminate). Infinite time skips the final
    passive-gold pad to ``t_max``.

    **Lane waves beyond the bundle:** if ``extrapolate_lane_waves`` is ``None`` (default),
    it is ``True`` when ``t_max`` is infinite and ``False`` otherwise. When ``True``, wave
    composition for index ``k`` is synthesized via :func:`~LoLPerfmon.sim.wave_schedule.wave_composition_at_index`
    whenever the bundle has no precomputed wave at ``k``. Set ``extrapolate_lane_waves=True``
    for long finite horizons that exceed the bundle’s wave list.
    """
    if champion_id not in data.champions:
        raise KeyError(champion_id)
    hook = purchase_hook if purchase_hook is not None else lane_purchase_hook
    profile = data.champions[champion_id]
    items = data.items
    rules = data.rules
    cfg = config_from_rules(data)
    t_end = t_max if t_max is not None else cfg.t_max_seconds
    if math.isinf(t_end) and early_stop is None:
        raise ValueError("t_max=inf requires early_stop so the simulation can terminate")
    if extrapolate_lane_waves is None:
        extrapolate_lane = math.isinf(t_end)
    else:
        extrapolate_lane = extrapolate_lane_waves
    starting_gold = float(rules.start_gold)

    state = SimulationState(
        time_seconds=0.0,
        gold=starting_gold,
        inventory=[],
        total_xp=0.0,
        level=1,
        buy_queue=list(policy.buy_order),
        total_gold_spent_on_items=0.0,
        total_shop_sell_gold=0.0,
        blocked_purchase_ids=set(),
    )
    resolved_jungle_starter: str | None = None
    jungle_sell_done = False
    if farm_mode == FarmMode.JUNGLE:
        resolved_jungle_starter = resolve_jungle_starter_item_id(data, jungle_starter_item_id)
        if not acquire_goal(state, resolved_jungle_starter, items):
            raise ValueError(
                f"Jungle starter {resolved_jungle_starter} could not be purchased at game start "
                f"(gold={starting_gold})."
            )
    cum = _cs_cumulative_by_wave(data)
    max_wave_index = max(cum.keys()) if cum else 0
    timeline: list[tuple[float, float, int]] = [(0.0, state.gold, state.level)]
    total_farm = 0.0
    total_lane_minion_farm = 0.0
    total_jungle_monster_farm = 0.0
    total_passive = 0.0
    total_lane_thr_sum = 0.0
    total_jungle_eff_sum = 0.0
    total_lane_minions_sum = 0.0
    total_jungle_monsters_sum = 0.0
    t_prev = 0.0
    ended_by_early_stop = False

    if farm_mode == FarmMode.LANE:
        k = 0
        while True:
            t_wave = rules.first_wave_spawn_seconds + k * rules.wave_interval_seconds
            if not math.isinf(t_end) and t_wave > t_end:
                break
            if not extrapolate_lane and k > max_wave_index:
                break
            pg = passive_gold_in_interval(t_prev, t_wave, cfg)
            state.gold += pg
            total_passive += pg
            state.time_seconds = t_wave
            _purchase_round(state, items, defer_purchases_until, hook)
            wave = data.wave_at_index(k)
            if wave is None and extrapolate_lane:
                wave = wave_composition_at_index(k)
            if wave is None:
                k += 1
                t_prev = t_wave
                continue
            stats = total_stats(profile, state.level, tuple(state.inventory), items)
            game_minute = t_wave / 60.0
            dps = effective_dps(profile, state.level, stats)
            if on_lane_clear_dps is not None:
                on_lane_clear_dps(t_wave, k, dps)
            ct = clear_time_seconds(wave, game_minute, data, dps)
            lane_win = lane_available_seconds(
                rules.wave_interval_seconds,
                rules.lane_engagement_overhead_seconds,
            )
            thr = throughput_ratio(ct, lane_win) * eta_lane
            total_lane_thr_sum += thr
            total_lane_minions_sum += thr * float(wave_minion_count(wave))
            gold_full = wave_gold_if_full_clear(wave, game_minute, data)
            gold_gain = gold_full * thr
            xp_gain = _xp_for_wave_fraction(wave, state.level, thr, rules)
            state.gold += gold_gain
            total_farm += gold_gain
            total_lane_minion_farm += gold_gain
            state.total_xp += xp_gain
            state.level = level_from_total_xp(state.total_xp, rules)
            _purchase_round(state, items, defer_purchases_until, hook)
            timeline.append((state.time_seconds, state.gold, state.level))
            if on_wave:
                on_wave(state, t_wave, k)
            t_prev = t_wave
            k += 1
            if early_stop is not None and early_stop(state):
                ended_by_early_stop = True
                break
    else:
        t_next = rules.jungle_base_cycle_seconds
        jk = 0
        while math.isinf(t_end) or t_next <= t_end:
            pg = passive_gold_in_interval(t_prev, t_next, cfg)
            state.gold += pg
            total_passive += pg
            state.time_seconds = t_next
            _purchase_round(state, items, defer_purchases_until, hook)
            stats = total_stats(profile, state.level, tuple(state.inventory), items)
            jdps = effective_dps(profile, state.level, stats)
            if on_jungle_clear_dps is not None:
                on_jungle_clear_dps(t_next, jk, jdps)
            cycle = jungle_cycle_seconds(profile, state.level, stats, data)
            eff = min(1.0, rules.jungle_base_cycle_seconds / max(cycle, 1e-9))
            total_jungle_eff_sum += eff
            total_jungle_monsters_sum += eff * float(rules.jungle_monsters_per_route)
            gold_gain = rules.jungle_base_route_gold * eff
            xp_gain = rules.jungle_base_route_xp * eff
            state.gold += gold_gain
            total_farm += gold_gain
            total_jungle_monster_farm += gold_gain
            state.total_xp += xp_gain
            state.level = level_from_total_xp(state.total_xp, rules)
            _purchase_round(state, items, defer_purchases_until, hook)
            if (
                resolved_jungle_starter is not None
                and not jungle_sell_done
                and jungle_sell_at_seconds is not None
                and t_next + 1e-9 >= jungle_sell_at_seconds
                and (not jungle_sell_only_after_level_18 or state.level >= 18)
            ):
                if sell_jungle_companion_once(state, resolved_jungle_starter, items):
                    jungle_sell_done = True
            timeline.append((state.time_seconds, state.gold, state.level))
            if on_wave:
                on_wave(state, t_next, -1)
            t_prev = t_next
            t_next += rules.jungle_base_cycle_seconds
            jk += 1
            if early_stop is not None and early_stop(state):
                ended_by_early_stop = True
                break

    if not ended_by_early_stop and not math.isinf(t_end) and t_prev < t_end:
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
        total_shop_sell_gold=state.total_shop_sell_gold,
        ended_by_early_stop=ended_by_early_stop,
        total_lane_throughput_units=total_lane_thr_sum,
        total_jungle_route_eff_units=total_jungle_eff_sum,
        total_lane_minions_cleared=total_lane_minions_sum,
        total_jungle_monsters_cleared=total_jungle_monsters_sum,
        total_lane_minion_farm_gold=total_lane_minion_farm,
        total_jungle_monster_farm_gold=total_jungle_monster_farm,
    )
