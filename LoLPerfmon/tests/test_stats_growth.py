"""Pytest entry points; logic lives in LoLPerfmon.validation_checks."""

from LoLPerfmon.validation_checks import (
    ValidationContext,
    check_attack_speed_volibear_style,
    check_growth_stat_level2_alistar_style,
)


def test_growth_stat_level2_alistar_style(ctx: ValidationContext) -> None:
    check_growth_stat_level2_alistar_style(ctx)


def test_attack_speed_volibear_style(ctx: ValidationContext) -> None:
    check_attack_speed_volibear_style(ctx)
