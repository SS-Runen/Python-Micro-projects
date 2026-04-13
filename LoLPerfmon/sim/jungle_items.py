"""
Jungle companion items (Data Dragon ``Jungle`` tag) and rule constants.

Treat evolution thresholds for Classic Summoner's Rift 5v5 are documented on the wiki
(Jungling § Jungle items); the abstract farm sim does not model treat counts or Smite
tiers—only item stats from Data Dragon affect clears.

Sell mechanics live in :mod:`simulator` to avoid import cycles.
"""

from __future__ import annotations

from .data_loader import GameDataBundle
from .models import ItemDef
from .sell_economy import STANDARD_SHOP_SELL_REFUND_FRACTION

# Same as :data:`STANDARD_SHOP_SELL_REFUND_FRACTION` (50% of ``total_cost``).
JUNGLE_COMPANION_SELL_REFUND_FRACTION = STANDARD_SHOP_SELL_REFUND_FRACTION

# https://wiki.leagueoflegends.com/en-us/Jungling — Classic 5v5 pet evolution treat counts.
SR_JUNGLE_COMPANION_EVOLVE_TREAT_THRESHOLDS: tuple[int, ...] = (15, 35)


def is_jungle_companion_item(it: ItemDef) -> bool:
    return "Jungle" in it.tags


def jungle_companion_item_ids_sorted(data: GameDataBundle) -> list[str]:
    return sorted(iid for iid, it in data.items.items() if is_jungle_companion_item(it))


def is_jungle_pet_companion_starter(it: ItemDef) -> bool:
    """
    True for modern **jungle pet** starters (Data Dragon tag set ``Jungle`` only), excluding
    trinkets, wards, consumables, and legacy jungle items that also carry ``Jungle``.
    """
    tags = list(it.tags)
    return tags == ["Jungle"]


def jungle_pet_companion_item_ids_sorted(data: GameDataBundle) -> list[str]:
    """Lexicographically sorted pet ids (e.g. Gustwalker, Mosstomper, Scorchclaw) for multi-starter search."""
    return sorted(iid for iid, it in data.items.items() if is_jungle_pet_companion_starter(it))


def resolve_jungle_starter_item_id(data: GameDataBundle, jungle_starter_item_id: str | None) -> str:
    if jungle_starter_item_id is not None:
        if jungle_starter_item_id not in data.items:
            raise KeyError(jungle_starter_item_id)
        if not is_jungle_companion_item(data.items[jungle_starter_item_id]):
            raise ValueError(f"Not a jungle companion item: {jungle_starter_item_id}")
        return jungle_starter_item_id
    ids = jungle_pet_companion_item_ids_sorted(data)
    if not ids:
        ids = jungle_companion_item_ids_sorted(data)
    if not ids:
        raise ValueError(
            "FarmMode.JUNGLE requires at least one item with tag 'Jungle' in the bundle "
            "(Data Dragon catalog or offline stub)."
        )
    return ids[0]


__all__ = [
    "JUNGLE_COMPANION_SELL_REFUND_FRACTION",
    "SR_JUNGLE_COMPANION_EVOLVE_TREAT_THRESHOLDS",
    "is_jungle_companion_item",
    "is_jungle_pet_companion_starter",
    "jungle_companion_item_ids_sorted",
    "jungle_pet_companion_item_ids_sorted",
    "resolve_jungle_starter_item_id",
]
