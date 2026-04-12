from __future__ import annotations

from .clear import effective_dps
from .config import FarmMode
from .data_loader import GameDataBundle
from .models import ChampionProfile
from .simulator import PurchasePolicy, SimResult, simulate
from .stats import StatBlock, total_stats


def marginal_farm_rate(
    profile: ChampionProfile,
    stats_before: StatBlock,
    stats_after: StatBlock,
    _data: GameDataBundle,
    _game_minute: float,
) -> float:
    """Local diagnostic: change in effective DPS proxy after a stat change."""
    d0 = effective_dps(profile, stats_before)
    d1 = effective_dps(profile, stats_after)
    return d1 - d0


def compare_purchase_timing(
    data: GameDataBundle,
    champion_id: str,
    farm_mode: FarmMode,
    buy_order: tuple[str, ...],
    t_buy_cutoff_seconds: float,
    eta_lane: float = 1.0,
    t_max: float | None = None,
) -> tuple[SimResult, SimResult, float]:
    """
    Counterfactual pair: A purchases whenever affordable; B defers purchases until
    game time reaches ``t_buy_cutoff_seconds`` (same ordered buy list afterward).
    Returns ``(result_A, result_B, final_gold_A - final_gold_B)``.
    """
    policy = PurchasePolicy(buy_order=buy_order)
    res_a = simulate(
        data,
        champion_id,
        farm_mode,
        policy,
        eta_lane=eta_lane,
        t_max=t_max,
        defer_purchases_until=None,
    )
    res_b = simulate(
        data,
        champion_id,
        farm_mode,
        policy,
        eta_lane=eta_lane,
        t_max=t_max,
        defer_purchases_until=t_buy_cutoff_seconds,
    )
    return res_a, res_b, res_a.final_gold - res_b.final_gold


def stats_with_hypothetical_item(
    data: GameDataBundle,
    profile: ChampionProfile,
    level: int,
    inventory: tuple[str, ...],
    extra_item_id: str,
) -> StatBlock:
    inv = inventory + (extra_item_id,) if extra_item_id in data.items else inventory
    return total_stats(profile, level, inv, data.items)
