"""
Classify Data Dragon coverage vs local simulation rules.

Official Riot Data Dragon JSON is authoritative for items/champions/spells when available;
see LoLPerfmon/DATA_SOURCES.md for hierarchy (wiki / offline only as fallbacks).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ddragon_fetch import item_def_from_ddragon_entry, item_on_summoners_rift_classic

# Keys read by champion_profile_from_ddragon from raw["stats"].
CHAMPION_STATS_USED: tuple[str, ...] = (
    "hp",
    "hpperlevel",
    "mp",
    "mpperlevel",
    "attackdamage",
    "attackdamageperlevel",
    "armor",
    "armorperlevel",
    "spellblock",
    "spellblockperlevel",
    "attackspeed",
    "attackspeedperlevel",
)

# Item ``stats`` keys consumed by _bonus_from_item_stats in ddragon_fetch.
ITEM_STATS_KEYS_MAPPED: frozenset[str] = frozenset(
    {
        "FlatPhysicalDamageMod",
        "FlatMagicDamageMod",
        "PercentAttackSpeedMod",
        "FlatHasteMod",
        "FlatAbilityHasteMod",
        "FlatHPPoolMod",
        "FlatMPPoolMod",
        "FlatArmorMod",
        "FlatSpellBlockMod",
    }
)


@dataclass
class ItemCatalogAudit:
    """Single pass over item.json ``data`` for SR (maps[\"11\"]) items."""

    patch_version: str
    total_sr_items: int
    item_ids_unmapped_nonzero_stats: list[str] = field(default_factory=list)
    item_ids_missing_gold_total: list[str] = field(default_factory=list)


@dataclass
class DDragonAuditReport:
    champion_warnings: dict[str, list[str]]
    item_catalog: ItemCatalogAudit | None
    local_rules_notes: list[str]
    kit_proxy_note: str
    summary_ok: bool


def audit_champion_raw(champion_id: str, raw: dict[str, Any]) -> list[str]:
    """Warnings for missing stats keys used by the sim; info lines for unused DD keys."""
    out: list[str] = []
    s = raw.get("stats")
    if not isinstance(s, dict):
        out.append(f"{champion_id}: missing or invalid stats block")
        return out
    for key in CHAMPION_STATS_USED:
        if key not in s:
            out.append(f"{champion_id}: stats[{key!r}] missing (defaults apply in champion_profile_from_ddragon)")
    for key, val in s.items():
        if key in CHAMPION_STATS_USED:
            continue
        if isinstance(val, (int, float)) and key not in ("crit", "critperlevel"):
            out.append(f"{champion_id}: stats[{key!r}] present in Data Dragon but not used by ChampionProfile")
    return out


def audit_item_raw(item_id: str, raw: dict[str, Any]) -> list[str]:
    """Per-item notes; prefer :func:`scan_summoners_rift_item_catalog` for full file."""
    out: list[str] = []
    gold = raw.get("gold") or {}
    if gold.get("total") is None:
        out.append(f"{item_id}: gold.total missing")
    if not item_on_summoners_rift_classic(raw):
        return out
    stats_raw = raw.get("stats") or {}
    if not isinstance(stats_raw, dict):
        return out
    for k, v in stats_raw.items():
        if not isinstance(v, (int, float)):
            continue
        if abs(float(v)) < 1e-9:
            continue
        if k not in ITEM_STATS_KEYS_MAPPED:
            out.append(f"{item_id}: unmapped nonzero stats[{k!r}]={v}")
    return out


def scan_summoners_rift_item_catalog(item_data: dict[str, Any], patch_version: str) -> ItemCatalogAudit:
    """One O(n) pass over ``item.json`` ``data`` for SR items."""
    raw_by_id: dict[str, dict[str, Any]] = item_data.get("data") or {}
    unmapped: list[str] = []
    missing_gold: list[str] = []
    n = 0
    for sid, raw in raw_by_id.items():
        if not isinstance(raw, dict):
            continue
        if not item_on_summoners_rift_classic(raw):
            continue
        n += 1
        g = raw.get("gold") or {}
        if g.get("total") is None:
            missing_gold.append(str(sid))
        msgs = audit_item_raw(str(sid), raw)
        if any("unmapped nonzero" in m for m in msgs):
            unmapped.append(str(sid))
    return ItemCatalogAudit(
        patch_version=patch_version,
        total_sr_items=n,
        item_ids_unmapped_nonzero_stats=sorted(unmapped),
        item_ids_missing_gold_total=sorted(missing_gold),
    )


def audit_rules_local() -> list[str]:
    """Rules not shipped as a single Data Dragon blob (documented locally)."""
    return [
        "Passive gold cadence, wave spawn schedule, SR XP-to-level: summoners_rift_rules.py",
        "Minion gold/HP tables and wave composition: minion_defaults.py + wave_schedule.py",
        "Champion level stat growth formula (growth_stat): stats.py (wiki-style curve)",
        "Clear DPS KitParams: generic per champion until spell parsing fills kit (ddragon_spell_parse)",
    ]


def kit_proxy_note() -> str:
    return (
        "KitParams (ad_weight, ap_weight, …) in champion_profile_from_ddragon are not from Data Dragon; "
        "spell-level scaling is parsed separately (ddragon_spell_parse). Compare wiki ability descriptions "
        "when results look wrong for AD champions."
    )


def build_ddragon_audit_report(
    version: str,
    champion_raw_by_id: dict[str, dict[str, Any]],
    item_json_full: dict[str, Any] | None,
) -> DDragonAuditReport:
    champ_warn: dict[str, list[str]] = {}
    summary_ok = True
    for cid, raw in champion_raw_by_id.items():
        w = audit_champion_raw(cid, raw)
        champ_warn[cid] = w
        if any("missing" in x and "stats[" in x for x in w):
            summary_ok = False
    item_audit = None
    if item_json_full is not None:
        item_audit = scan_summoners_rift_item_catalog(item_json_full, version)
    return DDragonAuditReport(
        champion_warnings=champ_warn,
        item_catalog=item_audit,
        local_rules_notes=audit_rules_local(),
        kit_proxy_note=kit_proxy_note(),
        summary_ok=summary_ok,
    )
