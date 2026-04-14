"""
Infer which offensive stats matter most for modeled **ability** waveclear, then filter / rank items.

Uses Data Dragon spell coefficients when :attr:`~LoLPerfmon.sim.models.ChampionProfile.spell_farm` is
present: picks the spell line with the largest **(AP coeff + AD coeff) / cooldown** at the reference
rank, then classifies **ap** vs **ad** vs **mixed** from that line’s AP vs AD weights. Falls back to
:class:`~LoLPerfmon.sim.models.KitParams` ``ap_weight`` / ``ad_weight`` when no spell model exists.

Item pools keep items whose flat stats plausibly feed that axis (AP: AP or AH; AD: AD, bonus AS, or AH;
mixed: any of those). Recipe **downward closure** from :mod:`item_heuristics` keeps components craftable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from .clear import effective_dps
from .config import FarmMode
from .item_heuristics import downward_recipe_closure
from .jungle_items import is_jungle_pet_companion_starter
from .models import ChampionProfile, ItemDef
from .spell_farm_model import SpellFarmCoefficients, SpellLine
from .stats import StatBlock, total_stats

PrimaryAxis = Literal["ap", "ad", "mixed"]

_RATIO_EPS = 1.05


def _line_mean_cd(sl: SpellLine) -> float:
    return float(sl.cooldown) if sl.cooldown > 0 else 8.0


def _dominant_spell_line_coeffs(
    sf: SpellFarmCoefficients, level: int, stat_block: StatBlock
) -> tuple[float, float, float]:
    """
    Return (ap_coeff, ad_coeff, line_score) for the spell line whose scaling magnitude / CD is largest
    under :meth:`~LoLPerfmon.sim.spell_farm_model.SpellFarmCoefficients.optimal_waveclear_rank_allocation`.
    """
    ranks = sf.optimal_waveclear_rank_allocation(
        level,
        stat_block.ability_power,
        stat_block.bonus_ability_power,
        stat_block.attack_damage,
        stat_block.bonus_attack_damage,
        stat_block.ability_haste,
    )
    best_score = -1.0
    best_ap = 0.0
    best_ad = 0.0
    for sl, rk in zip(sf.lines, ranks):
        if rk <= 0:
            continue
        ri = min(rk - 1, 4)
        cd = max(_line_mean_cd(sl), 0.35)
        apt = sl.ap_total_by_rank[ri] + sl.ap_bonus_by_rank[ri]
        adt = sl.ad_total_by_rank[ri] + sl.ad_bonus_by_rank[ri]
        mag = (apt + adt) / cd
        if mag > best_score:
            best_score = mag
            best_ap, best_ad = apt, adt
    return best_ap, best_ad, best_score


def infer_primary_ability_damage_axis(
    profile: ChampionProfile, *, level: int = 11, stat_block: StatBlock | None = None
) -> tuple[PrimaryAxis, float, float]:
    """
    Classify modeled ability farm DPS as primarily **AP**, **AD**, or **mixed**.

    Uses optimal waveclear skill ranks at ``level`` and ``stat_block`` (naked champion growth when omitted).
    Returns ``(axis, dominant_line_ap_coeff, dominant_line_ad_coeff)`` for diagnostics.
    """
    sf = profile.spell_farm
    if sf is not None and sf.lines:
        st = stat_block if stat_block is not None else total_stats(profile, level, (), {})
        ap_c, ad_c, mag = _dominant_spell_line_coeffs(sf, level, st)
        if mag <= 1e-12:
            return _axis_from_kit_only(profile.kit), ap_c, ad_c
        if ap_c > ad_c * _RATIO_EPS:
            return "ap", ap_c, ad_c
        if ad_c > ap_c * _RATIO_EPS:
            return "ad", ap_c, ad_c
        return "mixed", ap_c, ad_c
    return _axis_from_kit_only(profile.kit), 0.0, 0.0


def _axis_from_kit_only(kit) -> PrimaryAxis:
    from .models import KitParams

    assert isinstance(kit, KitParams)
    apw = float(kit.ap_weight)
    adw = float(kit.ad_weight)
    if apw > adw * _RATIO_EPS:
        return "ap"
    if adw > apw * _RATIO_EPS:
        return "ad"
    return "mixed"


def item_matches_primary_damage_axis(it: ItemDef, axis: PrimaryAxis) -> bool:
    """
    True if the item’s flat stats can affect modeled ability DPS on ``axis`` (non-zero contribution).

    AH affects spell rotation frequency; AP/AD/AS affect damage. Tank-only stats (HP/armor/MR/mana
    without offensive stats) are excluded for strict damage alignment.
    """
    s = it.stats
    ap = float(s.ability_power)
    ad = float(s.attack_damage)
    ah = float(s.ability_haste)
    bas = float(s.bonus_attack_speed_fraction)
    if axis == "ap":
        return ap > 1e-9 or ah > 1e-9
    if axis == "ad":
        return ad > 1e-9 or bas > 1e-9 or ah > 1e-9
    return ap > 1e-9 or ad > 1e-9 or ah > 1e-9 or bas > 1e-9


def filter_waveclear_catalog_stat_aligned(
    full_items: Mapping[str, ItemDef],
    farm_mode: FarmMode,
    profile: ChampionProfile,
    *,
    exclude_tags: frozenset[str] | None = None,
    require_tags: frozenset[str] | None = None,
    level: int = 11,
) -> dict[str, ItemDef]:
    """
    Same pipeline as :func:`~LoLPerfmon.sim.item_heuristics.filter_waveclear_item_catalog`, but **seed**
    items are only those :func:`item_matches_primary_damage_axis` for this champion’s inferred axis.
    Then :func:`~LoLPerfmon.sim.item_heuristics.downward_recipe_closure` restores components.

    If that would remove every seed (data oddity), falls back to the non-stat-aligned waveclear dict.
    """
    from .item_heuristics import filter_waveclear_item_catalog

    base = filter_waveclear_item_catalog(
        full_items, farm_mode, exclude_tags=exclude_tags, require_tags=require_tags
    )
    axis, _, _ = infer_primary_ability_damage_axis(profile, level=level)
    seeds = {iid for iid, it in base.items() if item_matches_primary_damage_axis(it, axis)}
    if not seeds:
        return base
    return downward_recipe_closure(seeds, full_items)


def rank_stat_aligned_items_by_modeled_dps_per_gold(
    profile: ChampionProfile,
    items_by_id: Mapping[str, ItemDef],
    *,
    level: int = 11,
) -> list[tuple[str, float, PrimaryAxis]]:
    """
    Sort item ids by :func:`~LoLPerfmon.sim.item_heuristics.modeled_dps_uplift_per_gold`, restricted to
    items matching :func:`item_matches_primary_damage_axis` for this champion’s axis. Returns rows
    ``(item_id, uplift_per_gold, axis)``.
    """
    from .item_heuristics import modeled_dps_uplift_per_gold

    axis, _, _ = infer_primary_ability_damage_axis(profile, level=level)
    rows: list[tuple[str, float, PrimaryAxis]] = []
    for iid in sorted(items_by_id.keys()):
        it = items_by_id[iid]
        if not item_matches_primary_damage_axis(it, axis):
            continue
        u = modeled_dps_uplift_per_gold(profile, iid, items_by_id, level=level)
        rows.append((iid, u, axis))
    rows.sort(key=lambda t: (-t[1], t[0]))
    return rows


def marginal_dps_along_build_order(
    profile: ChampionProfile,
    purchase_order: tuple[str, ...],
    items_by_id: Mapping[str, ItemDef],
    *,
    level: int = 11,
) -> list[dict[str, float | str | int]]:
    """
    Cumulative modeled :func:`~LoLPerfmon.sim.clear.effective_dps` after each purchase id (greedy order).

    Each row: ``step``, ``item_id``, ``dps_before``, ``dps_after``, ``delta_dps``,
    ``delta_dps_per_item_total_cost`` (marginal ΔDPS / ``ItemDef.total_cost`` for that id — sticker cost,
    not marginal recipe fee).
    """
    out: list[dict[str, float | str | int]] = []
    inv: list[str] = []
    for step, iid in enumerate(purchase_order, start=1):
        if iid not in items_by_id:
            continue
        it = items_by_id[iid]
        st0 = total_stats(profile, level, tuple(inv), items_by_id)
        d0 = effective_dps(profile, level, st0)
        inv.append(iid)
        st1 = total_stats(profile, level, tuple(inv), items_by_id)
        d1 = effective_dps(profile, level, st1)
        dd = d1 - d0
        out.append(
            {
                "step": step,
                "item_id": iid,
                "dps_before": d0,
                "dps_after": d1,
                "delta_dps": dd,
                "delta_dps_per_item_total_cost": dd / max(it.total_cost, 1e-9),
            }
        )
    return out


__all__ = [
    "PrimaryAxis",
    "infer_primary_ability_damage_axis",
    "item_matches_primary_damage_axis",
    "filter_waveclear_catalog_stat_aligned",
    "rank_stat_aligned_items_by_modeled_dps_per_gold",
    "marginal_dps_along_build_order",
]
