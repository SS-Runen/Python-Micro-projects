from __future__ import annotations

from typing import Any


STAT_MAP = {
    "FlatHPPoolMod": "hp",
    "FlatMPPoolMod": "mana",
    "FlatArmorMod": "armor",
    "FlatSpellBlockMod": "magic_resist",
    "FlatPhysicalDamageMod": "attack_damage",
    "FlatMagicDamageMod": "ability_power",
    "PercentAttackSpeedMod": "attack_speed",
}


def ddragon_item_to_record(item_id: str, raw: dict[str, Any]) -> dict[str, Any]:
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
        "source_provenance": {
            "source_name": "ddragon",
            "source_url": "",
            "fetched_at": "",
            "confidence": 0.9,
        },
    }
