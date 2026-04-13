"""
Metrics for **how fast** a champion clears waves (lane) or camp cycles (jungle) in this simulator.

The core game loop uses:

- **Lane:** ``throughput_ratio(clear_time, wave_interval)`` — fraction of a wave cleared per
  spawn interval. It caps at **1.0** when ``clear_time <= wave_interval`` (full wave per interval).
  Extra DPS beyond that does **not** increase modeled farm ticks (see ``throughput_ratio`` in
  ``clear.py``).
- **Jungle:** ``eff = min(1, base_cycle_seconds / jungle_cycle_seconds)`` — same idea: extra DPS
  past the point where ``eff == 1`` does not increase per-route gold.

So **“clear as fast as possible”** in this model is closely tied to **reaching that cap early**,
not to arbitrarily high DPS. Cheaper purchases can move that time left (earlier power); expensive
items move it right but may still win on **long-horizon income** or **ROI**.

This module records the **first simulated clock time** at which the lane or jungle efficiency
first reaches **≈1** (within ``saturate_eps``).
"""

from __future__ import annotations

from .clear import clear_time_seconds, lane_available_seconds, throughput_ratio
from .config import FarmMode
from .data_loader import GameDataBundle
from .simulator import PurchasePolicy, SimResult, simulate


def time_to_saturated_farm_throughput(
    data: GameDataBundle,
    champion_id: str,
    farm_mode: FarmMode,
    purchase_hook,
    *,
    eta_lane: float = 1.0,
    t_max: float | None = None,
    jungle_starter_item_id: str | None = None,
    saturate_eps: float = 1e-9,
) -> tuple[float | None, SimResult]:
    """
    Earliest game time (seconds) when modeled clear throughput hits its **cap** for the current
    mode, and the full :class:`~LoLPerfmon.sim.simulator.SimResult` from the same run.

    **Lane:** first ``t_wave`` where ``throughput_ratio × eta_lane >= 1 - saturate_eps``.
    **Jungle:** first cycle time where ``eff >= 1 - saturate_eps``.

    If the cap is never reached before ``t_max``, returns ``(None, res)``.
    """
    rules = data.rules
    first_t: float | None = None

    def lane_cb(t_wave: float, k: int, dps: float) -> None:
        nonlocal first_t
        if first_t is not None:
            return
        wave = data.wave_at_index(k)
        if wave is None:
            return
        gm = t_wave / 60.0
        ct = clear_time_seconds(wave, gm, data, dps)
        lane_win = lane_available_seconds(
            rules.wave_interval_seconds,
            rules.lane_engagement_overhead_seconds,
        )
        thr = throughput_ratio(ct, lane_win) * eta_lane
        if thr + saturate_eps >= 1.0:
            first_t = t_wave

    def jungle_cb(t_c: float, _jk: int, jdps: float) -> None:
        nonlocal first_t
        if first_t is not None:
            return
        base = rules.jungle_base_cycle_seconds
        ref = 80.0
        cycle = base * ref / max(jdps, 1e-6)
        eff = min(1.0, base / max(cycle, 1e-9))
        if eff + saturate_eps >= 1.0:
            first_t = t_c

    res = simulate(
        data,
        champion_id,
        farm_mode,
        PurchasePolicy(buy_order=()),
        eta_lane=eta_lane,
        t_max=t_max,
        purchase_hook=purchase_hook,
        on_lane_clear_dps=lane_cb if farm_mode == FarmMode.LANE else None,
        on_jungle_clear_dps=jungle_cb if farm_mode == FarmMode.JUNGLE else None,
        jungle_starter_item_id=jungle_starter_item_id,
    )
    return first_t, res


def farm_income_per_gold_spent(res: SimResult, epsilon: float = 1e-9) -> float:
    """``total_farm_gold / total_gold_spent_on_items`` — long-run return on shop spend."""
    return res.total_farm_gold / max(res.total_gold_spent_on_items, epsilon)


__all__ = [
    "farm_income_per_gold_spent",
    "time_to_saturated_farm_throughput",
]
