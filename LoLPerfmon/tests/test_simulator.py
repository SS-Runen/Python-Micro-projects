from LoLPerfmon.data.loaders import data_root_default, load_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.simulator import simulate_farm_horizon, simulate_with_buy_order


def test_simulate_lane_positive_gold():
    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    res = simulate_farm_horizon(
        ch["lux"],
        FarmMode.LANE,
        items,
        [None] * 6,
        120.0,
        lane_minion=units["lane_melee"],
    )
    assert res.total_farm_gold > 0
    assert res.passive_gold_total > 0


def test_buy_order_spends_and_clears_more():
    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    base = simulate_with_buy_order(
        ch["lux"],
        FarmMode.LANE,
        items,
        (),
        300.0,
        lane_minion=units["lane_melee"],
    )
    boosted = simulate_with_buy_order(
        ch["lux"],
        FarmMode.LANE,
        items,
        ("amplifying_tome", "amplifying_tome"),
        300.0,
        lane_minion=units["lane_melee"],
    )
    assert boosted.gold_spent > 0
    assert boosted.total_lane_minions_cleared >= base.total_lane_minions_cleared
