"""Ranked Summoner's Rift item catalog filter (Data Dragon shapes)."""

from __future__ import annotations

from LoLPerfmon.sim.ddragon_fetch import item_eligible_ranked_summoners_rift_5v5


def test_ranked_filter_keeps_purchasable_and_recipe_items() -> None:
    raw_by_id = {
        "1036": {
            "maps": {"11": True},
            "gold": {"total": 350, "purchasable": True},
            "from": [],
        },
        "3070": {
            "maps": {"11": True},
            "gold": {"total": 400, "purchasable": True},
            "from": ["1027"],
        },
    }
    assert item_eligible_ranked_summoners_rift_5v5(raw_by_id["1036"], raw_by_id)
    assert item_eligible_ranked_summoners_rift_5v5(raw_by_id["3070"], raw_by_id)


def test_ranked_filter_keeps_transform_with_real_parent() -> None:
    """Seraph's-style: no from, not purchasable, specialRecipe → Archangel's (depth + tags)."""
    raw_by_id = {
        "3003": {
            "maps": {"11": True},
            "gold": {"total": 3000, "purchasable": True},
            "from": ["3070", "3802"],
            "depth": 3,
            "tags": ["SpellDamage", "Mana"],
        },
        "3040": {
            "maps": {"11": True},
            "gold": {"total": 3000, "purchasable": False},
            "specialRecipe": 3003,
        },
    }
    assert item_eligible_ranked_summoners_rift_5v5(raw_by_id["3040"], raw_by_id)


def test_ranked_filter_drops_arena_spatula_style_augment_path() -> None:
    raw_by_id = {
        "663064": {
            "maps": {"11": True},
            "gold": {"total": 900, "purchasable": True},
            "tags": [],
        },
        "664403": {
            "maps": {"11": True},
            "gold": {"total": 2500, "purchasable": False},
            "specialRecipe": 663064,
        },
    }
    assert not item_eligible_ranked_summoners_rift_5v5(raw_by_id["664403"], raw_by_id)


def test_ranked_filter_drops_non_purchasable_grant_without_recipe() -> None:
    raw_by_id = {
        "2052": {
            "maps": {"11": True},
            "gold": {"total": 0, "purchasable": False},
        },
    }
    assert not item_eligible_ranked_summoners_rift_5v5(raw_by_id["2052"], raw_by_id)


def test_ranked_filter_drops_guardian_rotating_starter_maps() -> None:
    """Guardian's * line: SR on, Nexus Blitz off, rotating queue on (live Data Dragon shape)."""
    raw_by_id = {
        "3177": {
            "maps": {"11": True, "12": True, "21": False, "35": True},
            "gold": {"total": 950, "purchasable": True},
            "tags": ["Lane", "Damage"],
        },
    }
    assert not item_eligible_ranked_summoners_rift_5v5(raw_by_id["3177"], raw_by_id)
