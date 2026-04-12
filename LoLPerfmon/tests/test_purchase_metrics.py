"""Pytest entry points; logic lives in LoLPerfmon.validation_checks."""

from LoLPerfmon.validation_checks import ValidationContext, check_compare_purchase_timing


def test_compare_purchase_timing_returns_tuple(ctx: ValidationContext) -> None:
    check_compare_purchase_timing(ctx)
