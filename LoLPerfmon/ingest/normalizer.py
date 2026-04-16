from __future__ import annotations

import copy
import math
from typing import Any

from LoLPerfmon.ingest.wiki_items import normalize_item_display_name
from LoLPerfmon.ingest.wiki_parser import normalize_champion_id
from LoLPerfmon.ingest.provenance import utc_timestamp
from LoLPerfmon.sim.models import DiscrepancyRecord


STAT_MAP = {
    "FlatHPPoolMod": "hp",
    "FlatMPPoolMod": "mana",
    "FlatArmorMod": "armor",
    "FlatSpellBlockMod": "magic_resist",
    "FlatPhysicalDamageMod": "attack_damage",
    "FlatMagicDamageMod": "ability_power",
    "PercentAttackSpeedMod": "attack_speed",
}


def ddragon_item_to_record(
    item_id: str,
    raw: dict[str, Any],
    *,
    extra_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = str(raw.get("name", item_id))
    cost = float(raw.get("gold", {}).get("total", 0) or 0)
    stats_granted: dict[str, float] = {}
    for entry in raw.get("stats", {}) or {}:
        if not entry:
            continue
        val = float(raw["stats"][entry])
        key = STAT_MAP.get(entry, entry.lower())
        stats_granted[key] = stats_granted.get(key, 0.0) + val
    from_ = raw.get("from") or []
    into = raw.get("into") or []
    prov: dict[str, Any] = {
        "source_name": "ddragon",
        "source_url": "",
        "fetched_at": "",
        "confidence": 0.9,
    }
    if extra_provenance:
        prov = {**prov, **extra_provenance}
    return {
        "item_id": item_id,
        "name": name,
        "cost": cost,
        "stats_granted": stats_granted,
        "passive_tags": [],
        "builds_from": [str(x) for x in from_],
        "builds_into": [str(x) for x in into],
        "slot_cost": 1,
        "is_jungle_starter": "jungle" in name.lower(),
        "source_provenance": prov,
    }


def merge_item_wiki_ddragon_allowlist(
    data_obj: dict[str, Any],
    wiki_allowlist_normalized: set[str] | None,
    *,
    wiki_ok: bool,
    wiki_fallback: bool,
    patch: str,
    wiki_list_url: str = "",
) -> tuple[dict[str, dict[str, Any]], list[DiscrepancyRecord]]:
    """Intersect Data Dragon items with Wiki Classic SR allowlist by normalized display name.

    When *wiki_fallback* is True or *wiki_ok* is False, returns all DDragon items and sets
    ``wiki_fallback`` on provenance. Otherwise only items whose normalized name appears in
    the Wiki allowlist are included.
    """
    disc: list[DiscrepancyRecord] = []
    fetched_at = utc_timestamp()
    use_filter = wiki_ok and not wiki_fallback and wiki_allowlist_normalized is not None

    if not use_filter:
        out: dict[str, dict[str, Any]] = {}
        for iid, entry in data_obj.items():
            if not isinstance(entry, dict):
                continue
            sid = str(iid)
            out[sid] = ddragon_item_to_record(
                sid,
                entry,
                extra_provenance={
                    "source_name": "ddragon",
                    "fetched_at": fetched_at,
                    "patch_hint": patch,
                    "wiki_fallback": True,
                    "wiki_list_url": wiki_list_url,
                    "classic_sr_allowlist": None,
                    "parser_version": "ddragon_item_to_record_v1",
                },
            )
        return out, disc

    assert wiki_allowlist_normalized is not None
    allow = wiki_allowlist_normalized
    out = {}
    matched_norms: set[str] = set()
    for iid, entry in data_obj.items():
        if not isinstance(entry, dict):
            continue
        sid = str(iid)
        name = str(entry.get("name", sid))
        nn = normalize_item_display_name(name)
        if nn not in allow:
            continue
        matched_norms.add(nn)
        out[sid] = ddragon_item_to_record(
            sid,
            entry,
            extra_provenance={
                "source_name": "wiki+ddragon",
                "fetched_at": fetched_at,
                "patch_hint": patch,
                "wiki_fallback": False,
                "wiki_list_url": wiki_list_url,
                "classic_sr_allowlist": True,
                "parser_version": "ddragon_item_to_record_v1+wiki_sr_allowlist",
            },
        )

    wiki_only = sorted(allow - matched_norms)
    for w in wiki_only:
        disc.append(
            DiscrepancyRecord(
                entity_type="item",
                entity_id=w,
                field_path="name",
                canonical_value=None,
                candidate_value=w,
                source_name="wiki_vs_ddragon",
                delta_kind="missing",
                severity="medium",
                resolution_status="open",
            )
        )
    return out, disc


_CHAMP_STAT_KEYS = ("attack_damage", "ability_power", "attack_speed")


def ddragon_champion_to_record(
    full_json: dict[str, Any],
    champion_key: str,
    *,
    patch: str,
    source_url: str,
) -> dict[str, Any]:
    data_block = full_json.get("data") or {}
    block = data_block.get(champion_key)
    if not isinstance(block, dict):
        raise KeyError(champion_key)
    stats = block.get("stats") or {}
    if not isinstance(stats, dict):
        stats = {}
    cid = normalize_champion_id(str(block.get("id", champion_key)))
    name = str(block.get("name", champion_key))
    ad = float(stats.get("attackdamage") or 0)
    ad_g = float(stats.get("attackdamageperlevel") or 0)
    as_base = float(stats.get("attackspeed") or 0.625)
    as_pl = float(stats.get("attackspeedperlevel") or 0)
    as_g = as_pl / 100.0 if as_pl else 0.0
    tags = [str(t).lower() for t in (block.get("tags") or []) if t]
    if "mage" in tags or "support" in tags:
        primary = "ap"
        clear_tags: list[str] = ["ap"]
    elif "marksman" in tags:
        primary = "ad"
        clear_tags = ["ad"]
    else:
        primary = "ad"
        clear_tags = ["ad"]
    return {
        "champion_id": cid,
        "name": name,
        "role_modes_allowed": ["lane", "jungle"],
        "base_stats_at_level1": {
            "attack_damage": ad,
            "ability_power": 0.0,
            "attack_speed": as_base,
        },
        "growth_per_level": {
            "attack_damage": ad_g,
            "ability_power": 0.0,
            "attack_speed": as_g,
        },
        "ability_scaling_profile": {"primary_axis": primary},
        "clear_profile_tags": clear_tags,
        "source_provenance": {
            "source_name": "ddragon",
            "source_url": source_url,
            "fetched_at": utc_timestamp(),
            "patch_hint": patch,
            "parser_version": "ddragon_champion_to_record_v1",
            "confidence": 0.95,
        },
    }


def merge_champion_wiki_ddragon(
    dd_record: dict[str, Any],
    wiki_partial: dict[str, Any] | None,
    *,
    prefer_dd_on_conflict: bool = False,
) -> tuple[dict[str, Any], list[DiscrepancyRecord]]:
    """Overlay Wiki-parsed stats onto a Data Dragon record; log numeric disagreements."""
    merged = copy.deepcopy(dd_record)
    if not wiki_partial:
        return merged, []
    parsed_fields = set(wiki_partial.get("parsed_fields") or [])
    wiki_base = wiki_partial.get("base_stats_at_level1") or {}
    wiki_growth = wiki_partial.get("growth_per_level") or {}
    if not parsed_fields:
        return merged, []
    disc: list[DiscrepancyRecord] = []
    cid = str(merged.get("champion_id", ""))
    for field in _CHAMP_STAT_KEYS:
        if field not in parsed_fields or field not in wiki_base:
            continue
        wb = float(wiki_base[field])
        wg = float(wiki_growth.get(field, 0.0))
        mb = float(merged["base_stats_at_level1"][field])
        mg = float(merged["growth_per_level"][field])
        if not math.isclose(mb, wb, rel_tol=1e-4, abs_tol=1e-4) or not math.isclose(
            mg, wg, rel_tol=1e-4, abs_tol=1e-4
        ):
            disc.append(
                DiscrepancyRecord(
                    entity_type="champion",
                    entity_id=cid,
                    field_path=f"stats.{field}",
                    canonical_value={"base": mb, "growth": mg},
                    candidate_value={"base": wb, "growth": wg},
                    source_name="wiki_vs_ddragon",
                    delta_kind="numeric_drift",
                    severity="low",
                    resolution_status="accepted_wiki" if not prefer_dd_on_conflict else "accepted_ddragon",
                )
            )
        if prefer_dd_on_conflict:
            continue
        merged["base_stats_at_level1"][field] = wb
        merged["growth_per_level"][field] = wg
    prov = merged.get("source_provenance")
    if isinstance(prov, dict):
        prov["source_name"] = "wiki+ddragon"
        prov["parser_version"] = str(prov.get("parser_version", "")) + "+wiki_merge"
    merged["wiki_ddragon_discrepancies"] = [
        {
            "entity_type": d.entity_type,
            "entity_id": d.entity_id,
            "field_path": d.field_path,
            "canonical_value": d.canonical_value,
            "candidate_value": d.candidate_value,
            "source_name": d.source_name,
            "delta_kind": d.delta_kind,
            "severity": d.severity,
            "resolution_status": d.resolution_status,
        }
        for d in disc
    ]
    return merged, disc
