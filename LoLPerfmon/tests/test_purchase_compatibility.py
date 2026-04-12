"""blocked_purchase_ids + boots compatibility (League-style itemization)."""

from __future__ import annotations

from LoLPerfmon.sim.models import ItemDef, StatBonus
from LoLPerfmon.sim.simulator import SimulationState, acquire_goal


def test_single_copy_item_id_blocked_after_first_purchase() -> None:
    epic = ItemDef(
        "epic_a",
        "Epic A",
        400.0,
        StatBonus(ability_power=30.0),
        (),
        max_inventory_copies=1,
    )
    items = {"epic_a": epic}
    st = SimulationState(
        time_seconds=0.0,
        gold=5000.0,
        inventory=[],
        total_xp=0.0,
        level=1,
        buy_queue=[],
        total_gold_spent_on_items=0.0,
    )
    assert acquire_goal(st, "epic_a", items) is True
    assert "epic_a" in st.blocked_purchase_ids
    assert acquire_goal(st, "epic_a", items) is False


def test_boots_second_pair_blocked_while_first_in_inventory() -> None:
    boots1 = ItemDef(
        "b1",
        "Boots One",
        300.0,
        StatBonus(),
        (),
        tags=("Boots",),
        max_inventory_copies=1,
    )
    boots2 = ItemDef(
        "b2",
        "Boots Two",
        300.0,
        StatBonus(),
        (),
        tags=("Boots",),
        max_inventory_copies=1,
    )
    items = {"b1": boots1, "b2": boots2}
    st = SimulationState(
        time_seconds=0.0,
        gold=5000.0,
        inventory=["b1"],
        total_xp=0.0,
        level=1,
        buy_queue=[],
        total_gold_spent_on_items=0.0,
    )
    assert acquire_goal(st, "b2", items) is False


def test_crafting_releases_component_block_for_rebuy() -> None:
    comp = ItemDef("c", "Comp", 100.0, StatBonus(ability_power=10.0), (), max_inventory_copies=1)
    fin = ItemDef("f", "Fin", 300.0, StatBonus(ability_power=50.0), ("c",), max_inventory_copies=1)
    items = {"c": comp, "f": fin}
    st = SimulationState(
        time_seconds=0.0,
        gold=5000.0,
        inventory=[],
        total_xp=0.0,
        level=1,
        buy_queue=[],
        total_gold_spent_on_items=0.0,
    )
    assert acquire_goal(st, "c", items) is True
    assert "c" in st.blocked_purchase_ids
    assert acquire_goal(st, "f", items) is True
    assert "c" not in st.blocked_purchase_ids
    assert acquire_goal(st, "c", items) is True
