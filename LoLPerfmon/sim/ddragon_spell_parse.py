"""
Extract structured spell/passive fields from Data Dragon champion JSON.

Cooldowns, costs, and ``vars``/``effect`` are exposed for downstream modeling. Modern
patches often ship empty ``vars``; when present, entries follow ``{key, coeff: [...]}``.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from typing import Any

from .models import KitParams


@dataclass(frozen=True)
class SpellVariable:
    key: str
    coeffs: tuple[float, ...]


@dataclass(frozen=True)
class ParsedSpell:
    id: str
    name: str
    cooldown: tuple[float, ...]
    cost: tuple[float, ...]
    maxrank: int
    cost_type: str
    vars: tuple[SpellVariable, ...]
    effect: tuple[Any, ...]


@dataclass(frozen=True)
class ParsedPassive:
    name: str
    description: str


@dataclass(frozen=True)
class ChampionSpellData:
    champion_id: str
    passive: ParsedPassive | None
    spells: tuple[ParsedSpell, ...]


def _float_tuple(seq: Any) -> tuple[float, ...]:
    if not isinstance(seq, list):
        return ()
    out: list[float] = []
    for x in seq:
        try:
            out.append(float(x))
        except (TypeError, ValueError):
            out.append(0.0)
    return tuple(out)


def _parse_vars(raw_vars: Any) -> tuple[SpellVariable, ...]:
    if not isinstance(raw_vars, list) or not raw_vars:
        return ()
    out: list[SpellVariable] = []
    for entry in raw_vars:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key", ""))
        coeff_raw = entry.get("coeff")
        if isinstance(coeff_raw, list):
            coeffs = tuple(float(x) for x in coeff_raw if isinstance(x, (int, float)))
        else:
            coeffs = ()
        out.append(SpellVariable(key=key, coeffs=coeffs))
    return tuple(out)


def _parse_effect(raw_effect: Any) -> tuple[Any, ...]:
    if not isinstance(raw_effect, list):
        return ()
    return tuple(raw_effect)


def parse_spell_entry(spell_key: str, raw: dict[str, Any]) -> ParsedSpell:
    name = str(raw.get("name", spell_key))
    cd = _float_tuple(raw.get("cooldown"))
    cost = _float_tuple(raw.get("cost"))
    maxrank = int(raw.get("maxrank", 0) or 0)
    cost_type = str(raw.get("costType", "") or "")
    vr = _parse_vars(raw.get("vars"))
    eff = _parse_effect(raw.get("effect"))
    return ParsedSpell(
        id=str(raw.get("id", spell_key)),
        name=name,
        cooldown=cd,
        cost=cost,
        maxrank=maxrank,
        cost_type=cost_type,
        vars=vr,
        effect=eff,
    )


def parse_champion_spells(champion_key: str, raw: dict[str, Any]) -> ChampionSpellData:
    cid = champion_key.lower()
    passive_raw = raw.get("passive") or {}
    passive: ParsedPassive | None = None
    if isinstance(passive_raw, dict):
        passive = ParsedPassive(
            name=str(passive_raw.get("name", "Passive")),
            description=str(passive_raw.get("description", ""))[:4000],
        )
    spells_out: list[ParsedSpell] = []
    spells = raw.get("spells")
    if isinstance(spells, list):
        for i, sp in enumerate(spells):
            if isinstance(sp, dict):
                spells_out.append(parse_spell_entry(f"spell_{i}", sp))
    return ChampionSpellData(champion_id=cid, passive=passive, spells=tuple(spells_out))


_KIT_OVERRIDES: dict[str, KitParams] = {
    # AP mages: waveclear modeled as spell rotation; no auto-attack clear term (see lane_clear_dps).
    "lux": KitParams(
        ad_weight=0.0,
        ap_weight=1.0,
        as_weight=0.0,
        ah_weight=0.02,
        base_ability_dps=12.0,
        auto_attack_clear_weight=0.0,
    ),
    "karthus": KitParams(
        ad_weight=0.0,
        ap_weight=1.0,
        as_weight=0.0,
        ah_weight=0.02,
        base_ability_dps=14.0,
        auto_attack_clear_weight=0.0,
    ),
    "quinn": KitParams(
        ad_weight=1.0,
        ap_weight=0.0,
        as_weight=0.35,
        ah_weight=0.02,
        base_ability_dps=11.0,
        auto_attack_clear_weight=1.0,
    ),
}

_DEFAULT_KIT = KitParams(
    ad_weight=0.35,
    ap_weight=0.85,
    as_weight=0.25,
    ah_weight=0.02,
    base_ability_dps=11.0,
    auto_attack_clear_weight=1.0,
)


def _mean_cooldown(spell: ParsedSpell) -> float | None:
    if not spell.cooldown:
        return None
    return float(sum(spell.cooldown)) / max(len(spell.cooldown), 1)


def base_ability_dps_hint_from_mean_cooldown(mean_cd: float) -> float:
    """
    Bounded proxy for ability DPS from the mean spell cooldown (seconds).

    Used by :func:`kit_params_from_spells`; tested with table-driven oracles so the hook
    is not duplicated in tests.
    """
    return max(6.0, min(48.0, 110.0 / max(mean_cd, 0.4)))


def kit_params_from_spells(champion_key: str, spell_data: ChampionSpellData) -> KitParams:
    """
    Blend archetype defaults with a cooldown-aware ``base_ability_dps`` hint from parsed spells.
    AD/AP split is not inferred from tooltips here; use champion-specific overrides where needed.
    """
    base = _KIT_OVERRIDES.get(champion_key.lower(), _DEFAULT_KIT)
    cds = [m for s in spell_data.spells if (m := _mean_cooldown(s)) is not None and m > 1e-6]
    if not cds:
        return base
    avg_cd = sum(cds) / len(cds)
    dps = base_ability_dps_hint_from_mean_cooldown(avg_cd)
    return replace(base, base_ability_dps=dps)


def spell_data_to_kit_hint(data: ChampionSpellData) -> dict[str, float]:
    n_cd = sum(len(s.cooldown) for s in data.spells)
    return {"spell_count": float(len(data.spells)), "cooldown_entries": float(n_cd)}
