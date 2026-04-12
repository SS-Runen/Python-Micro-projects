"""Pytest entry points; logic lives in LoLPerfmon.validation_checks."""

from LoLPerfmon.validation_checks import (
    ValidationContext,
    check_defer_purchases_delays_spending,
    check_simulate_lane_increases_gold,
    check_simulate_passive_only_short_horizon,
)


def test_simulate_passive_only_short_horizon(ctx: ValidationContext) -> None:
    check_simulate_passive_only_short_horizon(ctx)


def test_simulate_lane_increases_gold(ctx: ValidationContext) -> None:
    check_simulate_lane_increases_gold(ctx)


def test_defer_purchases_delays_spending(ctx: ValidationContext) -> None:
    check_defer_purchases_delays_spending(ctx)
