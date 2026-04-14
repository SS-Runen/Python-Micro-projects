"""Primary AP/AD axis inference and stat-aligned pools."""

from __future__ import annotations

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.kit_stat_alignment import (
    infer_primary_ability_damage_axis,
    item_matches_primary_damage_axis,
    marginal_dps_along_build_order,
)
from LoLPerfmon.sim.models import ItemDef, KitParams, StatBonus


def test_infer_axis_generic_ap_kit() -> None:
    data = build_offline_bundle()
    p = data.champions["generic_ap"]
    axis, _, _ = infer_primary_ability_damage_axis(p, level=11)
    assert axis == "ap"


def test_item_matches_ap_axis() -> None:
    ap = ItemDef("a", "A", 100.0, StatBonus(ability_power=20.0), ())
    ad = ItemDef("b", "B", 100.0, StatBonus(attack_damage=20.0), ())
    assert item_matches_primary_damage_axis(ap, "ap") is True
    assert item_matches_primary_damage_axis(ad, "ap") is False


def test_marginal_dps_steps_monotonic_inventory() -> None:
    data = build_offline_bundle()
    p = data.champions["generic_ap"]
    items = data.items
    order = tuple(sorted(items.keys())[:3])
    rows = marginal_dps_along_build_order(p, order, items, level=6)
    assert len(rows) == len(order)
    assert rows[-1]["dps_after"] >= rows[0]["dps_before"] - 1e-9


def test_filter_stat_aligned_not_empty_offline() -> None:
    from LoLPerfmon.sim.kit_stat_alignment import filter_waveclear_catalog_stat_aligned

    data = build_offline_bundle()
    p = data.champions["generic_ap"]
    cat = filter_waveclear_catalog_stat_aligned(data.items, FarmMode.LANE, p, level=11)
    assert len(cat) >= 1
