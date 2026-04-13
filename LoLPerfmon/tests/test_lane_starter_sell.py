"""Lane starter resell (Doran's-style) during greedy acquisition."""

from __future__ import annotations

from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.greedy_farm_build import _greedy_purchase_burst
from LoLPerfmon.sim.models import ChampionProfile, ItemDef, StatBonus
from LoLPerfmon.sim.simulator import SimulationState, try_acquire_with_lane_starter_sells


def _minimal_profile() -> ChampionProfile:
    return ChampionProfile(
        id="p",
        base_health=600.0,
        growth_health=0.0,
        base_mana=400.0,
        growth_mana=0.0,
        base_attack_damage=55.0,
        growth_attack_damage=0.0,
        base_ability_power=0.0,
        growth_ability_power=0.0,
        base_armor=30.0,
        growth_armor=0.0,
        base_magic_resist=30.0,
        growth_magic_resist=0.0,
        base_attack_speed=0.65,
        attack_speed_ratio=0.0,
        bonus_attack_speed_growth=0.0,
    )


def test_try_acquire_sells_doran_for_slot_and_gold() -> None:
    doran = ItemDef(
        id="dr",
        name="Doran",
        total_cost=400.0,
        stats=StatBonus(ability_power=5.0),
        from_ids=(),
        into_ids=(),
        tags=("Lane",),
        max_inventory_copies=1,
    )
    fillers = [
        ItemDef(
            f"f{i}",
            f"F{i}",
            1.0,
            StatBonus(),
            (),
            into_ids=(),
            max_inventory_copies=6,
        )
        for i in range(5)
    ]
    big = ItemDef(
        "big",
        "Big",
        500.0,
        StatBonus(ability_power=50.0),
        (),
        into_ids=(),
    )
    items = {doran.id: doran, big.id: big, **{f.id: f for f in fillers}}
    state = SimulationState(
        time_seconds=100.0,
        gold=400.0,
        inventory=["dr", "f0", "f1", "f2", "f3", "f4"],
        total_xp=0.0,
        level=1,
        buy_queue=[],
        total_gold_spent_on_items=0.0,
    )
    assert try_acquire_with_lane_starter_sells(state, "big", items)
    assert "dr" not in state.inventory
    assert "big" in state.inventory
    assert state.gold + 1e-9 >= 400.0 + 200.0 - 500.0


def test_greedy_burst_can_replace_doran_with_higher_dps_item() -> None:
    doran = ItemDef(
        id="dr",
        name="Doran",
        total_cost=400.0,
        stats=StatBonus(ability_power=15.0),
        from_ids=(),
        into_ids=(),
        tags=("Lane",),
        max_inventory_copies=1,
    )
    fillers = [
        ItemDef(
            f"f{i}",
            f"F{i}",
            1.0,
            StatBonus(),
            (),
            into_ids=(),
            max_inventory_copies=6,
        )
        for i in range(5)
    ]
    upgrade = ItemDef(
        "up",
        "Upgrade",
        500.0,
        StatBonus(ability_power=80.0),
        (),
        into_ids=(),
    )
    items = {doran.id: doran, upgrade.id: upgrade, **{f.id: f for f in fillers}}
    profile = _minimal_profile()
    state = SimulationState(
        time_seconds=0.0,
        gold=400.0,
        inventory=["dr", "f0", "f1", "f2", "f3", "f4"],
        total_xp=0.0,
        level=1,
        buy_queue=[],
        total_gold_spent_on_items=0.0,
    )
    _greedy_purchase_burst(
        state,
        profile,
        items,
        None,
        1e-9,
        None,
        data=None,
        farm_mode=FarmMode.LANE,
        marginal_income_cap=False,
        endpoints_only_marginals=False,
        allow_lane_starter_sell=True,
    )
    assert "dr" not in state.inventory
    assert "up" in state.inventory
