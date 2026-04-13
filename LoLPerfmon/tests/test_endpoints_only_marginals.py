"""endpoints_only_marginals excludes DD leaf components (Tome, Long Sword, …)."""

from __future__ import annotations

from LoLPerfmon.sim.bundle_factory import build_offline_bundle
from LoLPerfmon.sim.greedy_farm_build import ranked_marginal_acquisitions
from LoLPerfmon.sim.models import ItemDef, StatBonus, is_pure_shop_component
from LoLPerfmon.sim.simulator import SimulationState


def test_is_pure_shop_component_fixture() -> None:
    tome = ItemDef(
        "tome",
        "Tome",
        400.0,
        StatBonus(ability_power=20.0),
        (),
        into_ids=("rylais",),
    )
    assert is_pure_shop_component(tome) is True
    ludens = ItemDef(
        "ludens",
        "Luden's",
        2600.0,
        StatBonus(ability_power=80.0),
        ("nlr", "lc"),
        into_ids=(),
        max_inventory_copies=1,
    )
    assert is_pure_shop_component(ludens) is False


def test_ranked_marginals_exclude_pure_components_when_flag() -> None:
    data = build_offline_bundle()
    profile = data.champions["generic_ap"]
    st = SimulationState(
        time_seconds=0.0,
        gold=5000.0,
        inventory=[],
        total_xp=0.0,
        level=1,
        buy_queue=[],
        total_gold_spent_on_items=0.0,
    )
    r0 = ranked_marginal_acquisitions(
        st,
        profile,
        data.items,
        1e-9,
        data=data,
        marginal_income_cap=False,
        endpoints_only_marginals=False,
    )
    r1 = ranked_marginal_acquisitions(
        st,
        profile,
        data.items,
        1e-9,
        data=data,
        marginal_income_cap=False,
        endpoints_only_marginals=True,
    )
    ids0 = {x[0] for x in r0}
    ids1 = {x[0] for x in r1}
    assert "cheap_ap" in ids0
    assert "cheap_ap" not in ids1
