"""
Spell rotation model for lane/jungle **ability** clear DPS from Data Dragon spell JSON.

**From Data Dragon (per spell):**

- ``cooldown`` — mean rank cooldown feeds rotation frequency.
- ``effect`` — base damage rows by rank where parsable.
- ``vars`` — scaling coefficients routed by key into **total vs bonus** AP and AD buckets.
- ``cost`` / ``costType`` — mean mana (or other) cost for sustain heuristics.

**Model:** each spell contributes ``(base + Σ coeff × stat) / effective_cd`` with League ability
haste on cooldown. Spells are summed **independently** (on-CD casts), not a strict GCD rotation.
Passives and many effects are ignored.

Auto-attacks are **not** included here; see :class:`KitParams.auto_attack_clear_weight` in
:func:`LoLPerfmon.sim.clear.lane_clear_dps`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ddragon_spell_parse import ChampionSpellData, ParsedSpell, SpellVariable
from .models import ChampionProfile


def _cooldown_with_ability_haste(base_seconds: float, ability_haste: float) -> float:
    """League: cooldown = base × 100 / (100 + Ability Haste). AH clamped at 0."""
    ah = max(0.0, float(ability_haste))
    return float(base_seconds) * 100.0 / (100.0 + ah)


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


def _var_bucket(key: str) -> str | None:
    """Route a Data Dragon ``vars`` key to ap_total, ap_bonus, ad_total, or ad_bonus."""
    k = key.lower()
    if "bonusattackdamage" in k or k == "fad":
        return "ad_bonus"
    if "attackdamage" in k or k in ("ad", "championattackdamage"):
        return "ad_total"
    if "bonus" in k and any(
        x in k for x in ("spelldamage", "magicdamage", "mds", "abilitypower")
    ):
        return "ap_bonus"
    if any(s in k for s in ("spelldamage", "magicdamage", "mds")):
        return "ap_total"
    if "abilitypower" in k or k == "ap":
        return "ap_total"
    return None


def _vars_scaling_by_rank(
    vars: tuple[SpellVariable, ...],
) -> tuple[
    tuple[float, ...],
    tuple[float, ...],
    tuple[float, ...],
    tuple[float, ...],
]:
    ap_t = [0.0, 0.0, 0.0, 0.0, 0.0]
    ap_b = [0.0, 0.0, 0.0, 0.0, 0.0]
    ad_t = [0.0, 0.0, 0.0, 0.0, 0.0]
    ad_b = [0.0, 0.0, 0.0, 0.0, 0.0]
    for v in vars:
        if not v.coeffs:
            continue
        coeffs = list(v.coeffs)
        while len(coeffs) < 5:
            coeffs.append(coeffs[-1] if coeffs else 0.0)
        coeffs = coeffs[:5]
        bucket = _var_bucket(v.key)
        if bucket == "ap_total":
            for i in range(5):
                ap_t[i] += coeffs[i]
        elif bucket == "ap_bonus":
            for i in range(5):
                ap_b[i] += coeffs[i]
        elif bucket == "ad_total":
            for i in range(5):
                ad_t[i] += coeffs[i]
        elif bucket == "ad_bonus":
            for i in range(5):
                ad_b[i] += coeffs[i]
    return (tuple(ap_t), tuple(ap_b), tuple(ad_t), tuple(ad_b))


def _mean_cd(spell: ParsedSpell) -> float:
    if not spell.cooldown:
        return 8.0
    return float(sum(spell.cooldown)) / max(len(spell.cooldown), 1)


def _mean_spell_cost(spell: ParsedSpell) -> tuple[float, str]:
    if not spell.cost:
        return 0.0, str(spell.cost_type or "")
    return (
        float(sum(spell.cost)) / max(len(spell.cost), 1),
        str(spell.cost_type or ""),
    )


@dataclass(frozen=True)
class SpellLine:
    cooldown: float
    base_by_rank: tuple[float, ...]
    ap_total_by_rank: tuple[float, float, float, float, float]
    ap_bonus_by_rank: tuple[float, float, float, float, float]
    ad_total_by_rank: tuple[float, float, float, float, float]
    ad_bonus_by_rank: tuple[float, float, float, float, float]
    resource_cost_mean: float = 0.0
    resource_cost_kind: str = ""


@dataclass(frozen=True)
class SpellFarmCoefficients:
    lines: tuple[SpellLine, ...]
    needs_kit_ap_fallback: bool
    needs_kit_ad_fallback: bool

    def rotation_ability_dps(
        self,
        level: int,
        ability_power_total: float,
        ability_power_bonus: float,
        attack_damage_total: float,
        attack_damage_bonus: float,
        ability_haste: float = 0.0,
    ) -> float:
        ri = _ability_rank_index(level)
        total = 0.0
        cd_floor = 0.35
        for sl in self.lines:
            raw_cd = max(_cooldown_with_ability_haste(sl.cooldown, ability_haste), cd_floor)
            if sl.base_by_rank:
                bi = min(ri, len(sl.base_by_rank) - 1)
                base = sl.base_by_rank[bi]
            else:
                base = 0.0
            apt = sl.ap_total_by_rank[ri]
            apb = sl.ap_bonus_by_rank[ri]
            adt = sl.ad_total_by_rank[ri]
            adb = sl.ad_bonus_by_rank[ri]
            hit = (
                base
                + apt * ability_power_total
                + apb * ability_power_bonus
                + adt * attack_damage_total
                + adb * attack_damage_bonus
            )
            total += hit / raw_cd
        return total


def mana_sustain_factor_on_rotation(
    profile: ChampionProfile,
    level: int,
    sf: SpellFarmCoefficients,
    ability_haste: float,
) -> float:
    """
    Scale theoretical spell DPS when mana spent per second (on-CD casts) exceeds modeled regen.

    Only applies when :attr:`ChampionProfile.resource_kind` is **Mana** (case-insensitive).
    Energy and resourceless champions are not throttled here.
    """
    if profile.resource_kind.strip().lower() != "mana":
        return 1.0
    from .stats import growth_stat

    mp_regen = growth_stat(profile.base_mp_regen, profile.growth_mp_regen, 0.0, level)
    if mp_regen <= 1e-6:
        return 1.0
    demand = 0.0
    for sl in sf.lines:
        ck = sl.resource_cost_kind.lower() if sl.resource_cost_kind else ""
        if ck and "mana" not in ck:
            continue
        if sl.resource_cost_mean <= 1e-12:
            continue
        cd_eff = max(_cooldown_with_ability_haste(sl.cooldown, ability_haste), 0.35)
        demand += sl.resource_cost_mean / cd_eff
    if demand <= 1e-12:
        return 1.0
    return min(1.0, max(0.0, mp_regen / demand))


def spell_farm_from_champion_data(spell_data: ChampionSpellData) -> SpellFarmCoefficients | None:
    lines: list[SpellLine] = []
    for sp in spell_data.spells:
        base = _extract_base_by_rank(sp.effect)
        ap_raw_t, ap_raw_b, ad_raw_t, ad_raw_b = _vars_scaling_by_rank(sp.vars)
        ap5t = _pad5(ap_raw_t)
        ap5b = _pad5(ap_raw_b)
        ad5t = _pad5(ad_raw_t)
        ad5b = _pad5(ad_raw_b)
        if (
            not base
            and sum(ap5t) < 1e-12
            and sum(ap5b) < 1e-12
            and sum(ad5t) < 1e-12
            and sum(ad5b) < 1e-12
        ):
            continue
        cm, ck = _mean_spell_cost(sp)
        lines.append(
            SpellLine(
                cooldown=_mean_cd(sp),
                base_by_rank=base if base else (),
                ap_total_by_rank=ap5t,
                ap_bonus_by_rank=ap5b,
                ad_total_by_rank=ad5t,
                ad_bonus_by_rank=ad5b,
                resource_cost_mean=cm,
                resource_cost_kind=ck,
            )
        )
    if not lines:
        return None
    ap_sum = sum(
        sum(sl.ap_total_by_rank) + sum(sl.ap_bonus_by_rank) for sl in lines
    )
    ad_sum = sum(
        sum(sl.ad_total_by_rank) + sum(sl.ad_bonus_by_rank) for sl in lines
    )
    return SpellFarmCoefficients(
        lines=tuple(lines),
        needs_kit_ap_fallback=ap_sum < 1e-9,
        needs_kit_ad_fallback=ad_sum < 1e-9,
    )
