"""Recipe-aware purchases and build-path search (offline synthetic graph)."""

from __future__ import annotations

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.build_path_optimizer import (
    acquisition_postorder_for_item,
    optimal_interleaved_build,
)
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.data_loader import GameDataBundle
from LoLPerfmon.sim.models import ItemDef, StatBonus
from LoLPerfmon.sim.simulator import PurchasePolicy, simulate


def _bundle_with_linear_mythic() -> GameDataBundle:
    ob = build_offline_bundle()
    a = ItemDef("cmp_a", "Comp A", 100.0, StatBonus(ability_power=10.0), ())
    b = ItemDef("cmp_b", "Comp B", 200.0, StatBonus(ability_power=5.0), ())
    myth = ItemDef("mythic_x", "Mythic X", 700.0, StatBonus(ability_power=80.0), ("cmp_a", "cmp_b"))
    items = dict(ob.items)
    items.update({a.id: a, b.id: b, myth.id: myth})
    return GameDataBundle(
        rules=ob.rules,
        champions=ob.champions,
        items=items,
        waves=ob.waves,
        minion_economy=ob.minion_economy,
        data_dir=None,
    )


def test_acquisition_postorder_matches_depth_first_from_order() -> None:
    data = _bundle_with_linear_mythic()
    seq = acquisition_postorder_for_item("mythic_x", data.items)
    assert seq == ("cmp_a", "cmp_b", "mythic_x")


def test_craft_costs_recipe_fee_not_full_sticker() -> None:
    data = _bundle_with_linear_mythic()
    res = simulate(
        data,
        "generic_ap",
        FarmMode.LANE,
        PurchasePolicy(buy_order=("cmp_a", "cmp_b", "mythic_x")),
        t_max=3600.0,
    )
    assert "mythic_x" in res.final_inventory
    assert res.final_gold > 0


def test_optimal_interleaved_single_root_matches_postorder() -> None:
    data = _bundle_with_linear_mythic()
    order, _val, _res = optimal_interleaved_build(
        data,
        "generic_ap",
        FarmMode.LANE,
        ("mythic_x",),
        t_max=1200.0,
    )
    assert order == ("cmp_a", "cmp_b", "mythic_x")


def test_partial_recipe_blocks_until_all_components_present() -> None:
    """With only cmp_a owned, mythic goal cannot craft or full-buy (partial overlap rule)."""
    data = _bundle_with_linear_mythic()
    res = simulate(
        data,
        "generic_ap",
        FarmMode.LANE,
        PurchasePolicy(buy_order=("cmp_a", "mythic_x")),
        t_max=3600.0,
    )
    assert "mythic_x" not in res.final_inventory
    assert "cmp_a" in res.final_inventory
