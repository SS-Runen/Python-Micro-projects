"""
Simulation validation checks for CI and AI agents.

Each ``check_*`` function raises AssertionError on failure with a human-readable message.
Use :func:`run_validation` to execute all checks and get a JSON-serializable report
without relying on pytest.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from LoLPerfmon.sim.bundle_factory import get_game_bundle
from LoLPerfmon.sim.clear import wave_gold_if_full_clear
from LoLPerfmon.sim.config import FarmMode, GameConfig
from LoLPerfmon.sim.data_loader import GameDataBundle, GameRules, cumulative_xp_thresholds, load_game_data
from LoLPerfmon.sim.optimizer import best_item_order_exhaustive
from LoLPerfmon.sim.passive import (
    passive_accumulated,
    passive_accumulated_discrete_half_second_steps,
    passive_gold_in_interval,
)
from LoLPerfmon.sim.purchase_metrics import compare_purchase_timing
from LoLPerfmon.sim.simulator import PurchasePolicy, config_from_rules, simulate
from LoLPerfmon.sim.stats import growth_stat, total_attack_speed
from LoLPerfmon.sim.summoners_rift_rules import SR_PASSIVE_GOLD_PER_10_SECONDS, SR_STARTING_GOLD
from LoLPerfmon.sim.test_champion_ids import (
    one_cheapest_item_id,
    primary_champion_id,
    two_cheapest_item_ids,
)
from LoLPerfmon.sim.xp_level import level_from_total_xp


@dataclass
class ValidationContext:
    """Shared fixtures for checks; lazy-loads game data once."""

    offline: bool = True
    _bundle: GameDataBundle | None = None

    @property
    def bundle(self) -> GameDataBundle:
        if self._bundle is None:
            self._bundle = get_game_bundle(offline=self.offline)
        return self._bundle

    @property
    def rules(self) -> GameRules:
        return self.bundle.rules


def check_passive_zero_before_105(_ctx: ValidationContext) -> None:
    cfg = GameConfig()
    assert passive_accumulated(30.0, cfg) == 0.0, "passive at 30s should be 0"
    assert passive_accumulated(65.0, cfg) == 0.0, "passive at exactly 65s should be 0 (starts after 1:05)"


def check_passive_linear_after_105(_ctx: ValidationContext) -> None:
    cfg = GameConfig()
    r = cfg.passive_rate_per_second()
    got = passive_accumulated(125.0, cfg)
    want = (125.0 - 65.0) * r
    assert math.isclose(got, want), f"passive at 125s: got {got}, want {want}"


def check_passive_interval_additive(_ctx: ValidationContext) -> None:
    cfg = GameConfig()
    a = passive_gold_in_interval(0.0, 200.0, cfg)
    b = passive_gold_in_interval(0.0, 100.0, cfg) + passive_gold_in_interval(100.0, 200.0, cfg)
    assert math.isclose(a, b), f"passive interval split mismatch: {a} vs {b}"


def check_discrete_matches_continuous(_ctx: ValidationContext) -> None:
    cfg = GameConfig()
    for t in [65.0, 66.0, 100.0, 3600.0]:
        c = passive_accumulated(t, cfg)
        d = passive_accumulated_discrete_half_second_steps(t, cfg)
        assert math.isclose(c, d, rel_tol=1e-12, abs_tol=1e-6), (
            f"discrete vs continuous at t={t}: {c} vs {d}"
        )


def check_growth_stat_level2_alistar_style(_ctx: ValidationContext) -> None:
    base, g, bonus, n = 685.0, 120.0, 0.0, 2
    expected = 685.0 + 120.0 * (2 - 1) * (0.7025 + 0.0175 * (2 - 1))
    got = growth_stat(base, g, bonus, n)
    assert math.isclose(got, expected), f"growth_stat: got {got}, expected {expected}"


def check_attack_speed_volibear_style(_ctx: ValidationContext) -> None:
    base_as, ratio, bonus_growth = 0.625, 0.7, 0.02
    bonus_from_items, n = 0.25, 3
    growth_term = bonus_growth * (n - 1) * (0.7025 + 0.0175 * (n - 1))
    bracket = bonus_from_items + growth_term
    expected = base_as + bracket * ratio
    got = total_attack_speed(base_as, ratio, bonus_growth, bonus_from_items, n)
    assert math.isclose(got, expected), f"total_attack_speed: got {got}, expected {expected}"


def check_game_bundle_rules(ctx: ValidationContext) -> None:
    data = ctx.bundle
    assert isinstance(data, GameDataBundle), "expected GameDataBundle"
    assert data.rules.start_gold == SR_STARTING_GOLD, "SR starting gold"
    assert data.rules.passive_gold_per_10_seconds == SR_PASSIVE_GOLD_PER_10_SECONDS
    g = data.gold_for_kill("melee", 7.5)
    assert g > 0, "melee gold at 7.5 min should be positive"


def check_wave_gold_hand_sum(ctx: ValidationContext) -> None:
    data = ctx.bundle
    wave = data.wave_at_index(0)
    assert wave is not None, "wave 0 must exist"
    minute = 35 / 60.0
    expected = 3 * data.gold_for_kill("melee", minute) + 3 * data.gold_for_kill("caster", minute)
    got = wave_gold_if_full_clear(wave, minute, data)
    assert abs(got - expected) < 1e-9, f"wave gold: got {got}, hand sum {expected}"


def check_level_thresholds_monotonic(ctx: ValidationContext) -> None:
    th = cumulative_xp_thresholds(ctx.rules.xp_to_next_level)
    assert th[0] == 0.0, "cumulative XP at level 1"
    assert th[1] == 280.0, "cumulative XP to reach level 2 (SR)"
    assert list(th) == sorted(th), "XP thresholds must be monotonic"


def check_level_from_total_xp(ctx: ValidationContext) -> None:
    r = ctx.rules
    assert level_from_total_xp(0.0, r) == 1
    assert level_from_total_xp(279.9, r) == 1
    assert level_from_total_xp(280.0, r) == 2
    assert level_from_total_xp(1e9, r) == 18


def check_simulate_passive_only_short_horizon(ctx: ValidationContext) -> None:
    data = ctx.bundle
    cid = primary_champion_id(data)
    cfg = config_from_rules(data)
    res = simulate(
        data,
        cid,
        FarmMode.LANE,
        PurchasePolicy(buy_order=()),
        t_max=34.0,
    )
    assert res.total_farm_gold == 0.0, "before first wave, farm gold should be 0"
    expected_passive = passive_accumulated(34.0, cfg)
    want_gold = data.rules.start_gold + expected_passive
    assert math.isclose(res.final_gold, want_gold), f"final gold {res.final_gold} vs {want_gold}"


def check_simulate_lane_increases_gold(ctx: ValidationContext) -> None:
    data = ctx.bundle
    cid = primary_champion_id(data)
    res = simulate(
        data,
        cid,
        FarmMode.LANE,
        PurchasePolicy(buy_order=()),
        t_max=400.0,
    )
    assert res.total_farm_gold > 0, "lane sim should accrue farm gold by 400s"
    assert res.final_level >= 1, "level should stay valid"


def check_defer_purchases_delays_spending(ctx: ValidationContext) -> None:
    data = ctx.bundle
    cid = primary_champion_id(data)
    iid = one_cheapest_item_id(data)
    pol = PurchasePolicy(buy_order=(iid,))
    early = simulate(data, cid, FarmMode.LANE, pol, t_max=300.0, defer_purchases_until=None)
    late = simulate(data, cid, FarmMode.LANE, pol, t_max=300.0, defer_purchases_until=200.0)
    assert iid in early.final_inventory, "early should buy cheapest item by 300s"
    assert len(late.final_inventory) == 0 or (early.final_gold != late.final_gold), (
        "defer should change outcome vs immediate buy"
    )


def check_exhaustive_optimizer(ctx: ValidationContext) -> None:
    data = ctx.bundle
    cid = primary_champion_id(data)
    a, b = two_cheapest_item_ids(data)
    order, val, res = best_item_order_exhaustive(
        data,
        cid,
        FarmMode.LANE,
        (a, b),
        t_max=600.0,
    )
    assert len(order) == 2, f"order length {len(order)}"
    assert val == res.final_gold, "optimizer score should match sim final_gold"


def check_compare_purchase_timing(ctx: ValidationContext) -> None:
    data = ctx.bundle
    cid = primary_champion_id(data)
    iid = one_cheapest_item_id(data)
    a, b, delta = compare_purchase_timing(
        data,
        cid,
        FarmMode.LANE,
        (iid,),
        t_buy_cutoff_seconds=500.0,
        t_max=800.0,
    )
    assert a.final_gold != b.final_gold or delta == 0.0, "counterfactual A/B should be comparable"


CHECKS: list[tuple[str, Callable[[ValidationContext], None]]] = [
    ("passive_zero_before_105", check_passive_zero_before_105),
    ("passive_linear_after_105", check_passive_linear_after_105),
    ("passive_interval_additive", check_passive_interval_additive),
    ("discrete_matches_continuous", check_discrete_matches_continuous),
    ("growth_stat_level2_alistar_style", check_growth_stat_level2_alistar_style),
    ("attack_speed_volibear_style", check_attack_speed_volibear_style),
    ("game_bundle_rules", check_game_bundle_rules),
    ("wave_gold_hand_sum", check_wave_gold_hand_sum),
    ("level_thresholds_monotonic", check_level_thresholds_monotonic),
    ("level_from_total_xp", check_level_from_total_xp),
    ("simulate_passive_only_short_horizon", check_simulate_passive_only_short_horizon),
    ("simulate_lane_increases_gold", check_simulate_lane_increases_gold),
    ("defer_purchases_delays_spending", check_defer_purchases_delays_spending),
    ("exhaustive_optimizer", check_exhaustive_optimizer),
    ("compare_purchase_timing", check_compare_purchase_timing),
]


def run_validation(
    data_dir: Path | None = None,
    offline: bool = True,
) -> list[dict[str, Any]]:
    """
    Run all checks; return a list of dicts with keys: id, ok, error (null if ok).

    If ``data_dir`` is set, load JSON from that directory (advanced). Otherwise
    use :func:`get_game_bundle` (``offline`` controls network use).
    """
    if data_dir is not None:
        ctx = ValidationContext(offline=offline, _bundle=load_game_data(data_dir))
    else:
        ctx = ValidationContext(offline=offline)
    out: list[dict[str, Any]] = []
    for check_id, fn in CHECKS:
        try:
            fn(ctx)
            out.append({"id": check_id, "ok": True, "error": None})
        except AssertionError as e:
            out.append({"id": check_id, "ok": False, "error": str(e)})
        except Exception as e:
            out.append({"id": check_id, "ok": False, "error": f"{type(e).__name__}: {e}"})
    return out


def validation_summary(report: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [r for r in report if not r["ok"]]
    return {
        "total": len(report),
        "passed": len(report) - len(failed),
        "failed": len(failed),
        "all_ok": len(failed) == 0,
        "failures": [{"id": r["id"], "error": r["error"]} for r in failed],
    }


def format_report(report: list[dict[str, Any]], style: str = "text") -> str:
    """``style`` is ``text`` (human) or ``json`` (one object per line for agents)."""
    summ = validation_summary(report)
    if style == "json":
        lines = [json.dumps(r, ensure_ascii=False) for r in report]
        lines.append(json.dumps({"summary": summ}, ensure_ascii=False))
        return "\n".join(lines)
    lines_out = [f"[{'PASS' if r['ok'] else 'FAIL'}] {r['id']}" for r in report]
    if summ["failures"]:
        lines_out.append("--- failures ---")
        for f in summ["failures"]:
            lines_out.append(f"  {f['id']}: {f['error']}")
    lines_out.append(f"--- summary: {summ['passed']}/{summ['total']} passed ---")
    return "\n".join(lines_out)


def main() -> None:
    import sys

    report = run_validation()
    summ = validation_summary(report)
    print(format_report(report, style="text"))
    sys.exit(0 if summ["all_ok"] else 1)


if __name__ == "__main__":
    main()
