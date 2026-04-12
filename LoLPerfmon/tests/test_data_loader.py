"""Pytest entry points; logic lives in LoLPerfmon.validation_checks."""

from LoLPerfmon.validation_checks import (
    ValidationContext,
    check_game_bundle_rules,
    check_wave_gold_hand_sum,
)


def test_game_bundle_rules(ctx: ValidationContext) -> None:
    check_game_bundle_rules(ctx)


def test_wave_gold_hand_sum_matches_loader(ctx: ValidationContext) -> None:
    check_wave_gold_hand_sum(ctx)
