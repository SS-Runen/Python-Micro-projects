from __future__ import annotations

from dataclasses import dataclass, field

from LoLPerfmon.sim.combat_throughput import effective_combat_stats, jungle_clear_dps, lane_clear_dps
from LoLPerfmon.sim.config import (
    FarmMode,
    HORIZONS_SEC,
    MAX_INVENTORY_SLOTS,
    PASSIVE_GOLD_AT_5MIN,
    STARTING_GOLD,
)
from LoLPerfmon.sim.economy import passive_gold_over_interval
from LoLPerfmon.sim.item_progression import (
    can_combine_recipe,
    combine_gold_cost,
    complete_recipe_in_inventory,
)
from LoLPerfmon.sim.models import ChampionStatic, ItemStatic, UnitStatic
from LoLPerfmon.sim.spawn_timeline import JungleCampSchedule, LaneWaveSchedule


@dataclass
class SimResult:
    total_farm_gold: float = 0.0
    total_lane_minions_cleared: float = 0.0
    total_jungle_monsters_cleared: float = 0.0
    passive_gold_total: float = 0.0
    gold_spent: float = 0.0
    final_wallet: float = 0.0
    checkpoints: dict[str, float] = field(default_factory=dict)
    final_inventory: tuple[str | None, ...] | None = None


def xp_for_level(level: int) -> float:
    return 100.0 * (level ** 1.5)


def level_from_xp(xp: float) -> int:
    lv = 1
    while lv < 18 and xp >= xp_for_level(lv + 1):
        lv += 1
    return lv


def lane_farm_tick(
    dps: float,
    minion: UnitStatic,
    wave: LaneWaveSchedule,
    dt: float,
) -> tuple[float, float]:
    hp = float(minion.base_hp_armor_mr.get("hp", 400.0))
    gold_per = float(minion.gold_xp_reward.get("gold", 20.0))
    if hp <= 0 or dps <= 0:
        return 0.0, 0.0
    time_per_kill = hp / dps
    kills_per_sec = 1.0 / time_per_kill
    minions_avail = (wave.minions_per_wave / wave.interval_sec) * dt
    cleared = min(minions_avail, kills_per_sec * dt)
    gold = cleared * gold_per
    return gold, cleared


def jungle_farm_tick(
    dps: float,
    monster: UnitStatic,
    sched: JungleCampSchedule,
    dt: float,
) -> tuple[float, float]:
    hp = float(monster.base_hp_armor_mr.get("hp", 400.0))
    gold_per = float(monster.gold_xp_reward.get("gold", 35.0))
    if hp <= 0 or dps <= 0:
        return 0.0, 0.0
    time_per_kill = hp / dps
    kills_per_sec = 1.0 / time_per_kill
    rate = sched.monsters_per_cycle / sched.cycle_sec
    monsters_avail = rate * dt
    cleared = min(monsters_avail, kills_per_sec * dt)
    return cleared * gold_per, cleared


def simulate_farm_horizon(
    champ: ChampionStatic,
    mode: FarmMode,
    items_catalog: dict[str, ItemStatic],
    inventory: list[str | None],
    t_max: float,
    *,
    lane_minion: UnitStatic | None = None,
    jungle_monster: UnitStatic | None = None,
    xp_gain_rate: float = 1.0,
    dt: float = 1.0,
) -> SimResult:
    if len(inventory) != MAX_INVENTORY_SLOTS:
        raise ValueError("inventory must be 6 slots")
    wallet = STARTING_GOLD
    spent = 0.0
    xp = 0.0
    level = 1
    farm_gold = 0.0
    passive_acc = 0.0
    lane_cleared = 0.0
    jungle_cleared = 0.0
    wave = LaneWaveSchedule()
    jsched = JungleCampSchedule()
    checkpoints: dict[str, float] = {}
    t = 0.0
    lm = lane_minion
    jm = jungle_monster
    while t < t_max:
        step = min(dt, t_max - t)
        passive_acc += passive_gold_over_interval(step)
        wallet += passive_gold_over_interval(step)
        stats = effective_combat_stats(champ, level, inventory, items_catalog)
        if mode == FarmMode.LANE:
            if lm is None:
                raise ValueError("lane_minion required for LANE mode")
            dps = lane_clear_dps(stats)
            g, c = lane_farm_tick(dps, lm, wave, step)
            farm_gold += g
            lane_cleared += c
            xp += c * float(lm.gold_xp_reward.get("xp", 60.0)) * 0.01 * xp_gain_rate
        else:
            if jm is None:
                raise ValueError("jungle_monster required for JUNGLE mode")
            dps = jungle_clear_dps(stats)
            g, c = jungle_farm_tick(dps, jm, jsched, step)
            farm_gold += g
            jungle_cleared += c
            xp += c * float(jm.gold_xp_reward.get("xp", 35.0)) * 0.02 * xp_gain_rate
        wallet += g
        new_lv = level_from_xp(xp)
        if new_lv != level:
            level = new_lv
        t += step
        for h in HORIZONS_SEC:
            if abs(t - h) < dt * 0.5 or (t >= h and t - step < h):
                key = f"farm_gold@{int(h)}s"
                if key not in checkpoints:
                    checkpoints[key] = farm_gold
    res = SimResult(
        total_farm_gold=farm_gold,
        total_lane_minions_cleared=lane_cleared,
        total_jungle_monsters_cleared=jungle_cleared,
        passive_gold_total=passive_acc,
        gold_spent=spent,
        final_wallet=wallet,
        checkpoints=checkpoints,
        final_inventory=tuple(inventory),
    )
    return res


def verify_passive_gold_at_5min() -> bool:
    return abs(passive_gold_over_interval(300.0) - PASSIVE_GOLD_AT_5MIN) < 1e-6


def _first_free_slot(inv: list[str | None]) -> int | None:
    for i, s in enumerate(inv):
        if s is None:
            return i
    return None


def simulate_with_buy_order(
    champ: ChampionStatic,
    mode: FarmMode,
    items_catalog: dict[str, ItemStatic],
    buy_order: tuple[str, ...],
    t_max: float,
    *,
    lane_minion: UnitStatic | None = None,
    jungle_monster: UnitStatic | None = None,
    dt: float = 1.0,
) -> SimResult:
    if mode == FarmMode.LANE and lane_minion is None:
        raise ValueError("lane_minion")
    if mode == FarmMode.JUNGLE and jungle_monster is None:
        raise ValueError("jungle_monster")
    inv: list[str | None] = [None] * MAX_INVENTORY_SLOTS
    wallet = STARTING_GOLD
    spent = 0.0
    xp = 0.0
    level = 1
    farm_gold = 0.0
    passive_acc = 0.0
    lane_cleared = 0.0
    jungle_cleared = 0.0
    wave = LaneWaveSchedule()
    jsched = JungleCampSchedule()
    checkpoints: dict[str, float] = {}
    buy_idx = 0
    t = 0.0
    lm = lane_minion
    jm = jungle_monster
    while t < t_max:
        step = min(dt, t_max - t)
        pg = passive_gold_over_interval(step)
        passive_acc += pg
        wallet += pg
        stats = effective_combat_stats(champ, level, inv, items_catalog)
        if mode == FarmMode.LANE and lm is not None:
            dps = lane_clear_dps(stats)
            g, c = lane_farm_tick(dps, lm, wave, step)
            farm_gold += g
            lane_cleared += c
            xp += c * float(lm.gold_xp_reward.get("xp", 60.0)) * 0.01
        elif mode == FarmMode.JUNGLE and jm is not None:
            dps = jungle_clear_dps(stats)
            g, c = jungle_farm_tick(dps, jm, jsched, step)
            farm_gold += g
            jungle_cleared += c
            xp += c * float(jm.gold_xp_reward.get("xp", 35.0)) * 0.02
        else:
            g = 0.0
        wallet += g
        level = level_from_xp(xp)
        while buy_idx < len(buy_order):
            iid = buy_order[buy_idx]
            if iid not in items_catalog:
                break
            it = items_catalog[iid]
            if it.builds_from and can_combine_recipe(inv, items_catalog, iid):
                combine_cost = combine_gold_cost(it, items_catalog)
                if wallet < combine_cost:
                    break
                wallet -= combine_cost
                spent += combine_cost
                inv[:] = complete_recipe_in_inventory(inv, items_catalog, iid)
                buy_idx += 1
                continue
            slot = _first_free_slot(inv)
            if slot is None or wallet < it.cost:
                break
            wallet -= it.cost
            spent += it.cost
            inv[slot] = iid
            buy_idx += 1
        t += step
        for h in HORIZONS_SEC:
            if t >= h and (t - step) < h:
                key = f"farm_gold@{int(h)}s"
                if key not in checkpoints:
                    checkpoints[key] = farm_gold
    return SimResult(
        total_farm_gold=farm_gold,
        total_lane_minions_cleared=lane_cleared,
        total_jungle_monsters_cleared=jungle_cleared,
        passive_gold_total=passive_acc,
        gold_spent=spent,
        final_wallet=wallet,
        checkpoints=checkpoints,
        final_inventory=tuple(inv),
    )
