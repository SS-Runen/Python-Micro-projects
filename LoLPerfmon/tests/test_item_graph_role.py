"""Deterministic item shop graph classification (endpoint vs component vs intermediate)."""

from __future__ import annotations

from LoLPerfmon.sim.models import ItemDef, StatBonus, item_graph_role


def test_item_graph_role_endpoint() -> None:
    it = ItemDef(
        id="x",
        name="x",
        total_cost=3000.0,
        stats=StatBonus(),
        from_ids=("a", "b"),
        into_ids=(),
    )
    assert item_graph_role(it) == "endpoint"


def test_item_graph_role_component() -> None:
    it = ItemDef(
        id="long",
        name="Long Sword",
        total_cost=350.0,
        stats=StatBonus(attack_damage=10.0),
        from_ids=(),
        into_ids=("parent",),
    )
    assert item_graph_role(it) == "component"


def test_item_graph_role_intermediate() -> None:
    it = ItemDef(
        id="mid",
        name="mid",
        total_cost=900.0,
        stats=StatBonus(ability_power=30.0),
        from_ids=("tome",),
        into_ids=("big",),
    )
    assert item_graph_role(it) == "intermediate"
