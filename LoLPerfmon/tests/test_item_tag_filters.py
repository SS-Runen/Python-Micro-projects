"""Tests for optional item catalog filtering by Data Dragon tags."""

from __future__ import annotations

from LoLPerfmon.sim.item_tag_filters import filter_items_by_tags
from LoLPerfmon.sim.models import ItemDef, StatBonus


def _item(iid: str, *tags: str) -> ItemDef:
    return ItemDef(
        id=iid,
        name=iid,
        total_cost=100.0,
        stats=StatBonus(),
        tags=tuple(tags),
    )


def test_exclude_support() -> None:
    items = {
        "a": _item("a", "Damage", "SpellDamage"),
        "b": _item("b", "Support", "Gold"),
    }
    out = filter_items_by_tags(items, exclude_tags={"Support"})
    assert set(out) == {"a"}


def test_require_damage() -> None:
    items = {"a": _item("a", "Damage"), "b": _item("b", "Tank")}
    out = filter_items_by_tags(items, require_tags={"Damage"})
    assert set(out) == {"a"}


def test_exclude_and_require_intersection() -> None:
    items = {
        "x": _item("x", "Damage"),
        "y": _item("y", "Support", "Damage"),
    }
    out = filter_items_by_tags(
        items, exclude_tags={"Support"}, require_tags={"Damage"}
    )
    assert set(out) == {"x"}


def test_empty_filters_returns_all() -> None:
    items = {"a": _item("a", "Support")}
    assert filter_items_by_tags(items) == items
