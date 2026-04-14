"""
Reachable Summoner's Rift skill-point allocations from Data Dragon–derived slot metadata.

`Data Dragon`_ champion spell JSON provides ``maxrank`` per spell and a fixed slot order (Q, W, E, R);
it does **not** list legal rank tuples. This module applies **Classic SR** reachability rules
(ultimate gates 6/11/16, levels 1–3 basic diversification) so waveclear DPS uses defensible
assignments only.

.. _Data Dragon: https://riot-api-libraries.readthedocs.io/en/latest/ddragon.html
"""

from __future__ import annotations

from functools import lru_cache

from .spell_farm_model import SpellLine, max_skill_points_for_ultimate


def _line_cap_slot(max_rank: int, is_ultimate: bool, champion_level: int) -> int:
    lv = max(1, min(18, champion_level))
    if is_ultimate:
        return min(max_rank, max_skill_points_for_ultimate(lv))
    return min(max_rank, 5)


def _slot_key(lines: tuple[SpellLine, ...]) -> tuple[tuple[int, bool], ...]:
    return tuple((sl.max_rank, sl.is_ultimate) for sl in lines)


def _diversification_ok(
    state: tuple[int, ...],
    level: int,
    slot_key: tuple[tuple[int, bool], ...],
) -> bool:
    """Levels 1–3: must unlock each basic once before any basic reaches rank 2 (three basics only)."""
    basics_idx = [i for i, (_, is_u) in enumerate(slot_key) if not is_u]
    if len(basics_idx) < 3:
        return True
    bcounts = [state[i] for i in basics_idx]
    if level == 1:
        return sum(bcounts) == 1 and max(bcounts, default=0) <= 1
    if level == 2:
        return sum(bcounts) == 2 and sorted(bcounts, reverse=True) == [1, 1, 0]
    if level == 3:
        return sum(bcounts) == 3 and all(x >= 1 for x in bcounts)
    return True


def _state_respects_caps(
    state: tuple[int, ...],
    level: int,
    slot_key: tuple[tuple[int, bool], ...],
) -> bool:
    for i, (mr, is_u) in enumerate(slot_key):
        if state[i] > _line_cap_slot(mr, is_u, level):
            return False
    return True


def _reachable_from_key(champion_level: int, slot_key: tuple[tuple[int, bool], ...]) -> frozenset[tuple[int, ...]]:
    lv = max(1, min(18, champion_level))
    n = len(slot_key)
    if n == 0:
        return frozenset()

    caps_sum = sum(_line_cap_slot(mr, is_u, lv) for mr, is_u in slot_key)
    target_sum = min(lv, caps_sum)

    # Level 1: one point in a basic slot only (ultimate locked before 6).
    current: set[tuple[int, ...]] = set()
    for i, (mr, is_u) in enumerate(slot_key):
        if is_u:
            continue
        s = [0] * n
        s[i] = 1
        t = tuple(s)
        if _state_respects_caps(t, 1, slot_key) and _diversification_ok(t, 1, slot_key):
            current.add(t)

    if target_sum == 0:
        return frozenset()
    if target_sum == 1:
        return frozenset(current)

    for level in range(2, target_sum + 1):
        nxt: set[tuple[int, ...]] = set()
        for st in current:
            for j in range(n):
                mr, is_u = slot_key[j]
                if st[j] >= _line_cap_slot(mr, is_u, level):
                    continue
                lst = list(st)
                lst[j] += 1
                t = tuple(lst)
                if not _state_respects_caps(t, level, slot_key):
                    continue
                if not _diversification_ok(t, level, slot_key):
                    continue
                nxt.add(t)
        current = nxt
        if not current:
            break

    return frozenset(s for s in current if sum(s) == target_sum)


@lru_cache(maxsize=512)
def _reachable_cached(champion_level: int, slot_key: tuple[tuple[int, bool], ...]) -> frozenset[tuple[int, ...]]:
    return _reachable_from_key(champion_level, slot_key)


def reachable_skill_allocations(
    champion_level: int,
    lines: tuple[SpellLine, ...],
) -> frozenset[tuple[int, ...]]:
    """
    All skill-point tuples reachable at ``champion_level`` under Classic SR rules.

    Inputs come from Data Dragon via :class:`~LoLPerfmon.sim.spell_farm_model.SpellLine`
    ``max_rank`` and ``is_ultimate`` (last spell slot = R). Rules are encoded here, not read
    from JSON.
    """
    if not lines:
        return frozenset()
    return _reachable_cached(champion_level, _slot_key(lines))


__all__ = ["reachable_skill_allocations"]
