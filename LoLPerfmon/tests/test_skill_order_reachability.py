"""Reachable SR skill tuples vs cap-only enumeration (levels 1–3 diversification, R gates)."""

from __future__ import annotations

from LoLPerfmon.sim.skill_order_reachability import reachable_skill_allocations
from LoLPerfmon.sim.spell_farm_model import SpellLine, _enumerate_skill_allocations_uncapped


def _qwer_lines() -> tuple[SpellLine, SpellLine, SpellLine, SpellLine]:
    z5 = (0.0, 0.0, 0.0, 0.0, 0.0)
    dead = SpellLine(
        cooldown=10.0,
        base_by_rank=(),
        ap_total_by_rank=z5,
        ap_bonus_by_rank=z5,
        ad_total_by_rank=z5,
        ad_bonus_by_rank=z5,
        max_rank=5,
        is_ultimate=False,
    )
    dead_r = SpellLine(
        cooldown=10.0,
        base_by_rank=(),
        ap_total_by_rank=z5,
        ap_bonus_by_rank=z5,
        ad_total_by_rank=z5,
        ad_bonus_by_rank=z5,
        max_rank=3,
        is_ultimate=True,
    )
    return (dead, dead, dead, dead_r)


def test_level2_double_basic_unreachable() -> None:
    lines = _qwer_lines()
    r = reachable_skill_allocations(2, lines)
    assert (2, 0, 0, 0) not in r
    assert (1, 1, 0, 0) in r


def test_level3_only_one_one_one_on_basics() -> None:
    lines = _qwer_lines()
    r = reachable_skill_allocations(3, lines)
    assert r == {(1, 1, 1, 0)}
    assert (2, 1, 0, 0) not in r


def test_r_second_rank_not_before_11() -> None:
    lines = _qwer_lines()
    r6 = reachable_skill_allocations(6, lines)
    assert any(t[3] == 1 for t in r6)
    r10 = reachable_skill_allocations(10, lines)
    assert all(t[3] <= 1 for t in r10)
    r11 = reachable_skill_allocations(11, lines)
    assert any(t[3] == 2 for t in r11)


def test_uncapped_includes_illegal_early_double() -> None:
    lines = _qwer_lines()
    uncapped = set(_enumerate_skill_allocations_uncapped(2, lines))
    reach = reachable_skill_allocations(2, lines)
    assert (2, 0, 0, 0) in uncapped
    assert (2, 0, 0, 0) not in reach
