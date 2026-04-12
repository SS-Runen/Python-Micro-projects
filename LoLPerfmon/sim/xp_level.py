from __future__ import annotations

from .data_loader import GameRules, cumulative_xp_thresholds


def level_from_total_xp(total_xp: float, rules: GameRules) -> int:
    thresholds = cumulative_xp_thresholds(rules.xp_to_next_level)
    level = 1
    for L in range(2, 19):
        if total_xp + 1e-9 >= thresholds[L - 1]:
            level = L
        else:
            break
    return min(level, 18)


def xp_for_minion_kill(minion_kind: str, level: int, rules: GameRules) -> float:
    idx = max(0, min(17, level - 1))
    if minion_kind == "melee":
        return rules.minion_xp_melee_by_level[idx]
    if minion_kind == "caster":
        return rules.minion_xp_caster_by_level[idx]
    if minion_kind == "siege":
        return rules.minion_xp_siege_by_level[idx]
    return 0.0
