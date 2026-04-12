"""Pytest entry points; logic lives in LoLPerfmon.validation_checks."""

from LoLPerfmon.validation_checks import (
    ValidationContext,
    check_level_from_total_xp,
    check_level_thresholds_monotonic,
)


def test_level_thresholds_monotonic(ctx: ValidationContext) -> None:
    check_level_thresholds_monotonic(ctx)


def test_level_from_total_xp(ctx: ValidationContext) -> None:
    check_level_from_total_xp(ctx)
