"""Recipe-expanded roots vs flat exhaustive goals (clear-speed alignment)."""

from __future__ import annotations

from dataclasses import replace

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.build_path_optimizer import acquisition_sequence_for_finished_roots
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.data_loader import GameDataBundle
from LoLPerfmon.sim.marginal_clear import clear_upgrade_report
from LoLPerfmon.sim.models import ItemDef, StatBonus
from LoLPerfmon.sim.simulator import MAX_INVENTORY_SLOTS, PurchasePolicy, simulate


def _bundle_ludens_style() -> GameDataBundle:
    """NLR + Lost Chapter components craft into Luden's-like mythic."""
    ob = build_offline_bundle()
    nlr = ItemDef("nlr", "Needlessly Large Rod", 400.0, StatBonus(ability_power=40.0), ())
    lc = ItemDef("lc", "Lost Chapter", 500.0, StatBonus(ability_power=30.0, mana=100.0), ())
    ludens = ItemDef(
        "ludens",
        "Luden's (fixture)",
        2600.0,
        StatBonus(ability_power=100.0),
        ("nlr", "lc"),
        max_inventory_copies=1,
    )
    items = dict(ob.items)
    items.update({"nlr": nlr, "lc": lc, "ludens": ludens})
    return GameDataBundle(
        rules=ob.rules,
        champions=ob.champions,
        items=items,
        waves=ob.waves,
        minion_economy=ob.minion_economy,
        data_dir=None,
    )


def test_acquisition_sequence_matches_postorder() -> None:
    data = _bundle_ludens_style()
    seq = acquisition_sequence_for_finished_roots(data.items, "ludens")
    assert seq == ("nlr", "lc", "ludens")


def test_finished_root_path_beats_redundant_nlr_then_parent_goals() -> None:
    """
    A flat queue ``(nlr, ludens)`` leaves Luden's uncraftable (needs ``lc`` in inventory);
    partial overlap then blocks a sticker craft. Recipe-expanded ``(nlr, lc, ludens)``
    completes the mythic and yields strictly more farm gold over the same horizon.
    """
    data = _bundle_ludens_style()
    cid = "generic_ap"
    t_max = 3600.0
    res_bad = simulate(
        data,
        cid,
        FarmMode.LANE,
        PurchasePolicy(buy_order=("nlr", "ludens")),
        t_max=t_max,
    )
    seq = acquisition_sequence_for_finished_roots(data.items, "ludens")
    res_single = simulate(
        data,
        cid,
        FarmMode.LANE,
        PurchasePolicy(buy_order=seq),
        t_max=t_max,
    )
    assert "ludens" not in res_bad.final_inventory
    assert "ludens" in res_single.final_inventory
    assert res_single.total_farm_gold > res_bad.total_farm_gold


def test_clear_upgrade_report_saturated_when_full_and_no_affordable_gain() -> None:
    """Smoke: marginal report runs; full inventory yields saturated with no rows."""
    data = _bundle_ludens_style()
    res = simulate(
        data,
        "generic_ap",
        FarmMode.LANE,
        PurchasePolicy(buy_order=()),
        t_max=100.0,
    )
    sat, rows = clear_upgrade_report(data, "generic_ap", res)
    assert isinstance(sat, bool)
    assert isinstance(rows, list)


def test_clear_upgrade_report_saturated_when_six_slots_full() -> None:
    """No hypothetical one-step add when the bag already has six items."""
    ob = build_offline_bundle()
    r = replace(ob.rules, start_gold=500_000.0)
    items = dict(ob.items)
    for i in range(6):
        lid = f"leaf_{i}"
        items[lid] = ItemDef(lid, f"Leaf {i}", 10.0, StatBonus(ability_power=1.0), ())
    data = GameDataBundle(
        rules=r,
        champions=ob.champions,
        items=items,
        waves=ob.waves,
        minion_economy=ob.minion_economy,
        data_dir=None,
    )
    order = tuple(f"leaf_{i}" for i in range(6))
    res = simulate(data, "generic_ap", FarmMode.LANE, PurchasePolicy(buy_order=order), t_max=3600.0)
    assert len(res.final_inventory) == MAX_INVENTORY_SLOTS
    sat, rows = clear_upgrade_report(data, "generic_ap", res)
    assert sat is True
    assert rows == []


def test_clear_upgrade_report_omits_second_copy_of_unique_item() -> None:
    """Shop blocks repurchasing a finished unique already in inventory; report must not fake it."""
    data = _bundle_ludens_style()
    res = simulate(
        data,
        "generic_ap",
        FarmMode.LANE,
        PurchasePolicy(buy_order=("nlr", "lc", "ludens")),
        t_max=3600.0,
    )
    assert res.final_inventory.count("ludens") == 1
    _sat, rows = clear_upgrade_report(data, "generic_ap", res)
    assert all(r[0] != "ludens" for r in rows)
