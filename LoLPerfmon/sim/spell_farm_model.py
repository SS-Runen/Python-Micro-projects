"""
Spell rotation model for lane/jungle **ability** clear DPS from Data Dragon spell JSON.

**From Data Dragon (per spell):**

- ``cooldown`` — mean rank cooldown feeds rotation frequency.
- ``effect`` — base damage rows by rank where parsable.
- ``vars`` — scaling coefficients routed by key into **total vs bonus** AP and AD buckets.
- ``cost`` / ``costType`` — mean mana (or other) cost for sustain heuristics.

**Model:** each spell contributes ``(base + Σ coeff × stat) / effective_cd`` with League ability
haste on cooldown. Spells are summed **independently** (on-CD casts), not a strict GCD rotation.
Skill points (one per champion level, Q/W/E max 5, R max 3 with unlocks at 6/11/16) are assigned to
**maximize** this rotation proxy for waveclear at the modeled stats. Assignments are **reachable**
under Classic SR rules (see :mod:`~LoLPerfmon.sim.skill_order_reachability`); Data Dragon supplies
``maxrank`` and slot order only, not legal tuples. Passives and many effects are ignored.

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
    """Deprecated single-rank proxy: map level to one 0..4 index (legacy tests only)."""
    lv = max(1, min(18, level))
    return max(0, min(4, (lv - 1) // 3))


def max_skill_points_for_ultimate(champion_level: int) -> int:
    """League: R ranks 1–3 unlock at champion levels 6 / 11 / 16."""
    lv = max(1, min(18, champion_level))
    if lv < 6:
        return 0
    if lv < 11:
        return 1
    if lv < 16:
        return 2
    return 3


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
    #: Max skill points storable on this ability (5 for Q/W/E, 3 for R in Summoner's Rift).
    max_rank: int = 5
    #: True when this line is the champion's ultimate in Data Dragon order (last spell slot).
    is_ultimate: bool = False
    resource_cost_mean: float = 0.0
    resource_cost_kind: str = ""


def _line_hit_damage(
    sl: SpellLine,
    points: int,
    ability_power_total: float,
    ability_power_bonus: float,
    attack_damage_total: float,
    attack_damage_bonus: float,
) -> float:
    if points <= 0:
        return 0.0
    ri = min(points - 1, 4)
    if sl.base_by_rank:
        bi = min(ri, len(sl.base_by_rank) - 1)
        base = sl.base_by_rank[bi]
    else:
        base = 0.0
    apt = sl.ap_total_by_rank[ri]
    apb = sl.ap_bonus_by_rank[ri]
    adt = sl.ad_total_by_rank[ri]
    adb = sl.ad_bonus_by_rank[ri]
    return (
        base
        + apt * ability_power_total
        + apb * ability_power_bonus
        + adt * attack_damage_total
        + adb * attack_damage_bonus
    )


def _line_skill_cap(sl: SpellLine, champion_level: int) -> int:
    if sl.is_ultimate:
        return min(sl.max_rank, max_skill_points_for_ultimate(champion_level))
    return min(sl.max_rank, 5)


def _enumerate_skill_allocations_uncapped(
    champion_level: int,
    lines: tuple[SpellLine, ...],
) -> list[tuple[int, ...]]:
    """
    Legacy: all tuples with ``sum r_i == min(level, sum caps)`` and per-line caps **without**
    level-up reachability (levels 1–3 diversification). For tests / diagnostics only.
    """
    lv = max(1, min(18, champion_level))
    n = len(lines)
    if n == 0:
        return []
    caps = tuple(_line_skill_cap(lines[i], lv) for i in range(n))
    cap_sum = sum(caps)
    alloc_total = min(lv, cap_sum)
    out: list[tuple[int, ...]] = []

    def rec(i: int, rem: int, acc: list[int]) -> None:
        if i == n:
            if rem == 0:
                out.append(tuple(acc))
            return
        hi = min(caps[i], rem)
        for p in range(0, hi + 1):
            acc.append(p)
            rec(i + 1, rem - p, acc)
            acc.pop()

    rec(0, alloc_total, [])
    return out


@dataclass(frozen=True)
class SpellFarmCoefficients:
    lines: tuple[SpellLine, ...]
    needs_kit_ap_fallback: bool
    needs_kit_ad_fallback: bool
    def optimal_waveclear_rank_allocation(
        self,
        level: int,
        ability_power_total: float,
        ability_power_bonus: float,
        attack_damage_total: float,
        attack_damage_bonus: float,
        ability_haste: float = 0.0,
    ) -> tuple[int, ...]:
        """
        Skill points that maximize modeled rotation DPS (sum of per-spell hit / CD) at ``level``.

        One point per champion level; Q/W/E capped at ``max_rank`` (≤ 5), R at ≤ 3 with unlocks at 6/11/16.
        Tie-break: lexicographically larger tuple so results are stable.
        """
        from .skill_order_reachability import reachable_skill_allocations

        allocs = reachable_skill_allocations(level, self.lines)
        if not allocs:
            return tuple(0 for _ in self.lines)
        best: tuple[int, ...] | None = None
        best_val = -1.0
        for a in allocs:
            v = self.rotation_raw_dps_for_ranks(
                a,
                ability_power_total,
                ability_power_bonus,
                attack_damage_total,
                attack_damage_bonus,
                ability_haste,
            )
            if best is None:
                best_val = v
                best = a
                continue
            if v > best_val + 1e-15 or (abs(v - best_val) <= 1e-15 and a > best):
                best_val = v
                best = a
        assert best is not None
        return best

    def rotation_raw_dps_for_ranks(
        self,
        ranks: tuple[int, ...],
        ability_power_total: float,
        ability_power_bonus: float,
        attack_damage_total: float,
        attack_damage_bonus: float,
        ability_haste: float,
    ) -> float:
        if len(ranks) != len(self.lines):
            return 0.0
        total = 0.0
        cd_floor = 0.35
        for sl, rk in zip(self.lines, ranks):
            hit = _line_hit_damage(
                sl,
                rk,
                ability_power_total,
                ability_power_bonus,
                attack_damage_total,
                attack_damage_bonus,
            )
            raw_cd = max(_cooldown_with_ability_haste(sl.cooldown, ability_haste), cd_floor)
            total += hit / raw_cd
        return total

    def rotation_ability_dps(
        self,
        level: int,
        ability_power_total: float,
        ability_power_bonus: float,
        attack_damage_total: float,
        attack_damage_bonus: float,
        ability_haste: float = 0.0,
    ) -> float:
        ranks = self.optimal_waveclear_rank_allocation(
            level,
            ability_power_total,
            ability_power_bonus,
            attack_damage_total,
            attack_damage_bonus,
            ability_haste,
        )
        return self.rotation_raw_dps_for_ranks(
            ranks,
            ability_power_total,
            ability_power_bonus,
            attack_damage_total,
            attack_damage_bonus,
            ability_haste,
        )


def mana_sustain_factor_on_rotation(
    profile: ChampionProfile,
    level: int,
    sf: SpellFarmCoefficients,
    ability_haste: float,
    ranks: tuple[int, ...] | None = None,
) -> float:
    """
    Scale theoretical spell DPS when mana spent per second (on-CD casts) exceeds modeled regen.

    Only applies when :attr:`ChampionProfile.resource_kind` is **Mana** (case-insensitive).
    Energy and resourceless champions are not throttled here.

    If ``ranks`` is set (parallel to ``sf.lines``), only abilities with at least one rank
    contribute to mana demand.
    """
    if profile.resource_kind.strip().lower() != "mana":
        return 1.0
    from .stats import growth_stat

    mp_regen = growth_stat(profile.base_mp_regen, profile.growth_mp_regen, 0.0, level)
    if mp_regen <= 1e-6:
        return 1.0
    demand = 0.0
    for i, sl in enumerate(sf.lines):
        if ranks is not None:
            if i >= len(ranks) or ranks[i] <= 0:
                continue
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
    n_spells = len(spell_data.spells)
    last_dd_index = n_spells - 1
    for idx, sp in enumerate(spell_data.spells):
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
        # R is only the last slot when Q/W/E/R are all present; a single-spell excerpt is not R.
        is_ult = n_spells > 1 and idx == last_dd_index
        mr = int(sp.maxrank) if sp.maxrank else (3 if is_ult else 5)
        max_rank = max(1, min(3 if is_ult else 5, mr))
        lines.append(
            SpellLine(
                cooldown=_mean_cd(sp),
                base_by_rank=base if base else (),
                ap_total_by_rank=ap5t,
                ap_bonus_by_rank=ap5b,
                ad_total_by_rank=ad5t,
                ad_bonus_by_rank=ad5b,
                max_rank=max_rank,
                is_ultimate=is_ult,
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
