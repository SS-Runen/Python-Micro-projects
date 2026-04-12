"""
Spell rotation model for lane/jungle **ability** clear DPS from Data Dragon spell JSON.

Uses per-spell ``effect`` base damage rows and ``vars`` coeff lists where present.
Auto-attacks are **not** included here; see :class:`KitParams.auto_attack_clear_weight` in
:func:`LoLPerfmon.sim.clear.lane_clear_dps`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ddragon_spell_parse import ChampionSpellData, SpellVariable


def _ability_rank_index(level: int) -> int:
    """Map champion level 1..18 to 0..4 spell rank index (standard skill order approximation)."""
    lv = max(1, min(18, level))
    return max(0, min(4, (lv - 1) // 3))


def _pad5(t: tuple[float, ...]) -> tuple[float, float, float, float, float]:
    if not t:
        return (0.0, 0.0, 0.0, 0.0, 0.0)
    xs = list(t[:5])
    while len(xs) < 5:
        xs.append(xs[-1])
    return (xs[0], xs[1], xs[2], xs[3], xs[4])


def _extract_base_by_rank(effect: tuple) -> tuple[float, ...]:
    for cell in effect:
        if isinstance(cell, list) and cell:
            nums: list[float] = []
            for x in cell:
                if isinstance(x, (int, float)):
                    nums.append(float(x))
            if len(nums) >= 2:
                return tuple(nums[:5])
    return ()


def _vars_ap_ad_by_rank(vars: tuple[SpellVariable, ...]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    ap = [0.0, 0.0, 0.0, 0.0, 0.0]
    ad = [0.0, 0.0, 0.0, 0.0, 0.0]
    for v in vars:
        if not v.coeffs:
            continue
        coeffs = list(v.coeffs)
        while len(coeffs) < 5:
            coeffs.append(coeffs[-1] if coeffs else 0.0)
        coeffs = coeffs[:5]
        k = v.key.lower()
        if any(s in k for s in ("spelldamage", "magicdamage", "mds")):
            for i in range(5):
                ap[i] += coeffs[i]
        elif any(s in k for s in ("attackdamage", "bonusattackdamage", "fad")):
            for i in range(5):
                ad[i] += coeffs[i]
    return tuple(ap), tuple(ad)


def _mean_cd(spell: ParsedSpell) -> float:
    if not spell.cooldown:
        return 8.0
    return float(sum(spell.cooldown)) / max(len(spell.cooldown), 1)


@dataclass(frozen=True)
class SpellLine:
    cooldown: float
    base_by_rank: tuple[float, ...]
    ap_by_rank: tuple[float, float, float, float, float]
    ad_by_rank: tuple[float, float, float, float, float]


@dataclass(frozen=True)
class SpellFarmCoefficients:
    lines: tuple[SpellLine, ...]
    needs_kit_ap_fallback: bool
    needs_kit_ad_fallback: bool

    def rotation_ability_dps(self, level: int, ability_power: float, attack_damage: float) -> float:
        ri = _ability_rank_index(level)
        total = 0.0
        cd_floor = 0.35
        for sl in self.lines:
            cd = max(sl.cooldown, cd_floor)
            if sl.base_by_rank:
                bi = min(ri, len(sl.base_by_rank) - 1)
                base = sl.base_by_rank[bi]
            else:
                base = 0.0
            ap_r = sl.ap_by_rank[ri]
            ad_r = sl.ad_by_rank[ri]
            total += (base + ap_r * ability_power + ad_r * attack_damage) / cd
        return total


def spell_farm_from_champion_data(spell_data: ChampionSpellData) -> SpellFarmCoefficients | None:
    lines: list[SpellLine] = []
    for sp in spell_data.spells:
        base = _extract_base_by_rank(sp.effect)
        ap_raw, ad_raw = _vars_ap_ad_by_rank(sp.vars)
        ap5 = _pad5(ap_raw)
        ad5 = _pad5(ad_raw)
        if not base and sum(ap5) < 1e-12 and sum(ad5) < 1e-12:
            continue
        lines.append(
            SpellLine(
                cooldown=_mean_cd(sp),
                base_by_rank=base if base else (),
                ap_by_rank=ap5,
                ad_by_rank=ad5,
            )
        )
    if not lines:
        return None
    ap_sum = sum(sum(sl.ap_by_rank) for sl in lines)
    ad_sum = sum(sum(sl.ad_by_rank) for sl in lines)
    return SpellFarmCoefficients(
        lines=tuple(lines),
        needs_kit_ap_fallback=ap_sum < 1e-9,
        needs_kit_ad_fallback=ad_sum < 1e-9,
    )
