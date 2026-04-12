"""Pytest entry points; logic lives in LoLPerfmon.validation_checks."""

from LoLPerfmon.validation_checks import ValidationContext, check_exhaustive_optimizer


def test_exhaustive_runs(ctx: ValidationContext) -> None:
    check_exhaustive_optimizer(ctx)
