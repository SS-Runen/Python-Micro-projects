"""
Post-simulation marginal clear / DPS checks (buy-only; no sell/replace in this module).

Used to report whether another valid shop acquisition could still increase ``effective_dps``
given final level, inventory, and gold. For sell-then-buy paths use :func:`~LoLPerfmon.sim.simulator.sell_item_once`
with a copied state.
"""

from __future__ import annotations

from .clear import effective_dps
from .data_loader import GameDataBundle
from .models import ItemDef
from .simulator import (
    MAX_INVENTORY_SLOTS,
    SimResult,
    SimulationState,
    acquire_goal,
    blocked_purchase_ids_from_inventory,
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


def _state_from_farm_result(res: SimResult, items: dict[str, ItemDef]) -> SimulationState:
    inv = list(res.final_inventory)
    return SimulationState(
        time_seconds=0.0,
        gold=float(res.final_gold),
        inventory=inv,
        total_xp=0.0,
        level=int(res.final_level),
        buy_queue=[],
        total_gold_spent_on_items=0.0,
        blocked_purchase_ids=blocked_purchase_ids_from_inventory(inv, items),
    )


def clear_upgrade_report(
    data: GameDataBundle,
    champion_id: str,
    res: SimResult,
) -> tuple[bool, list[tuple[str, float, float]]]:
    """
    After a run, try each catalog item once via :func:`acquire_goal` on a snapshot of
    ``final_gold``, ``final_inventory``, and reconstructed ``blocked_purchase_ids`` (same
    duplicate rules as the live simulator).

    Returns ``(saturated, rows)`` where ``rows`` are ``(item_id, delta_effective_dps, gold_paid)``
    for acquisitions that succeed and increase **modeled** ``effective_dps``, sorted by delta
    descending.

    ``saturated`` is True when no such row exists. If the bag has no free slot
    (``len(inventory) >= MAX_INVENTORY_SLOTS``), returns ``(True, [])``.

    Does not model selling or replacement paths beyond one :func:`acquire_goal` call per item id.
    """
    if champion_id not in data.champions:
        raise KeyError(champion_id)
    profile = data.champions[champion_id]
    items = data.items
    inv = list(res.final_inventory)
    lvl = int(res.final_level)

    if len(inv) >= MAX_INVENTORY_SLOTS:
        return True, []

    base_state = _state_from_farm_result(res, items)
    base_stats = total_stats(profile, lvl, tuple(base_state.inventory), items)
    base_dps = effective_dps(profile, lvl, base_stats)

    rows: list[tuple[str, float, float]] = []
    for iid in sorted(items.keys()):
        trial = _snapshot_state(base_state)
        spent_before = trial.total_gold_spent_on_items
        if not acquire_goal(trial, iid, items):
            continue
        paid = trial.total_gold_spent_on_items - spent_before
        st1 = total_stats(profile, lvl, tuple(trial.inventory), items)
        delta = effective_dps(profile, lvl, st1) - base_dps
        if delta > 1e-12:
            rows.append((iid, delta, paid))

    rows.sort(key=lambda t: -t[1])
    return (len(rows) == 0, rows)


__all__ = ["clear_upgrade_report"]
