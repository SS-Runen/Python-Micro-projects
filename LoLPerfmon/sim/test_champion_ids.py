"""Resolve champion / item ids for tests against any :class:`GameDataBundle`."""

from __future__ import annotations

from .data_loader import GameDataBundle


def primary_champion_id(data: GameDataBundle) -> str:
    for k in ("lux", "karthus", "quinn", "generic_ap"):
        if k in data.champions:
            return k
    return next(iter(data.champions))


def two_cheapest_item_ids(data: GameDataBundle) -> tuple[str, str]:
    ids = sorted(data.items.keys(), key=lambda i: data.items[i].total_cost)
    if len(ids) < 2:
        raise ValueError("bundle needs at least two items for this check")
    return (ids[0], ids[1])


def one_cheapest_item_id(data: GameDataBundle) -> str:
    ids = sorted(data.items.keys(), key=lambda i: data.items[i].total_cost)
    return ids[0]
