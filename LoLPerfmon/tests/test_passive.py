"""Pytest entry points; logic lives in LoLPerfmon.validation_checks."""

from LoLPerfmon.validation_checks import (
    ValidationContext,
    check_discrete_matches_continuous,
    check_passive_interval_additive,
    check_passive_linear_after_105,
    check_passive_zero_before_105,
)


def test_passive_zero_before_105(ctx: ValidationContext) -> None:
    check_passive_zero_before_105(ctx)


def test_passive_linear_after_105(ctx: ValidationContext) -> None:
    check_passive_linear_after_105(ctx)


def test_passive_interval_additive(ctx: ValidationContext) -> None:
    check_passive_interval_additive(ctx)


def test_discrete_matches_continuous_at_sample_times(ctx: ValidationContext) -> None:
    check_discrete_matches_continuous(ctx)
