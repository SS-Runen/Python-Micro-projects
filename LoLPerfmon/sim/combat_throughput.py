from __future__ import annotations

from LoLPerfmon.sim.models import ChampionStatic, ItemStatic, level_stats


def sum_item_stats(inventory: list[str | None], items: dict[str, ItemStatic]) -> dict[str, float]:
    acc: dict[str, float] = {}
    for slot in inventory:
        if not slot or slot not in items:
            continue
        for k, v in items[slot].stats_granted.items():
            acc[k] = acc.get(k, 0.0) + v
    return acc


def effective_combat_stats(
    champ: ChampionStatic,
    level: int,
    inventory: list[str | None],
    items: dict[str, ItemStatic],
) -> dict[str, float]:
    base = level_stats(champ, level)
    extra = sum_item_stats(inventory, items)
    out = dict(base)
    for k, v in extra.items():
        out[k] = out.get(k, 0.0) + v
    return out


def lane_clear_dps(stats: dict[str, float]) -> float:
    ad = stats.get("attack_damage", 0.0)
    ap = stats.get("ability_power", 0.0)
    atk_spd = max(0.1, stats.get("attack_speed", 0.625))
    auto = ad * atk_spd
    spell = ap * 0.4
    return auto + spell


def jungle_clear_dps(stats: dict[str, float]) -> float:
    return lane_clear_dps(stats) * 1.05
