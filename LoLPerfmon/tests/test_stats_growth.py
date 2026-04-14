"""Pytest entry points; logic lives in LoLPerfmon.validation_checks."""

from LoLPerfmon.sim.stats import clamp_champion_level
from LoLPerfmon.validation_checks import (
    ValidationContext,
    check_attack_speed_volibear_style,
    check_growth_stat_level2_alistar_style,
)


def test_growth_stat_level2_alistar_style(ctx: ValidationContext) -> None:
    check_growth_stat_level2_alistar_style(ctx)


def test_attack_speed_volibear_style(ctx: ValidationContext) -> None:
    check_attack_speed_volibear_style(ctx)


def test_clamp_champion_level_bounds() -> None:
    assert clamp_champion_level(0) == 1
    assert clamp_champion_level(1) == 1
    assert clamp_champion_level(18) == 18
    assert clamp_champion_level(99) == 18
