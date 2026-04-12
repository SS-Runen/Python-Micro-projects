"""
Frozen excerpts of real Data Dragon JSON for tests and :mod:`LoLPerfmon.validation_checks`.

Patch **14.23.1** (Riot CDN). Not live-updated — validates parsers and audits only.
"""

from __future__ import annotations

from typing import Any

# Lux: ``stats`` + ``passive`` + Q only — from ``/cdn/14.23.1/data/en_US/champion/Lux.json``.
LUX_CHAMPION_EXCERPT: dict[str, Any] = {
    "stats": {
        "hp": 580,
        "hpperlevel": 99,
        "mp": 480,
        "mpperlevel": 23.5,
        "armor": 21,
        "armorperlevel": 5.2,
        "spellblock": 30,
        "spellblockperlevel": 1.3,
        "movespeed": 330,
        "attackdamage": 54,
        "attackdamageperlevel": 3.3,
        "attackspeed": 0.669,
        "attackspeedperlevel": 3.0,
    },
    "passive": {
        "name": "Illumination",
        "description": "Lux's damaging spells charge the target with energy.",
    },
    "spells": [
        {
            "id": "LuxLightBinding",
            "name": "Light Binding",
            "maxrank": 5,
            "cooldown": [11, 10.5, 10, 9.5, 9],
            "cost": [50, 50, 50, 50, 50],
            "costType": " Mana",
            "vars": [],
            "effect": [None, [80, 120, 160, 200, 240]],
        }
    ],
}

# Minimal ``item.json``-shaped blob: two SR items, one with unmapped stat.
ITEM_JSON_EXCERPT: dict[str, Any] = {
    "type": "item",
    "version": "14.23.1",
    "data": {
        "1001": {
            "name": "Boots",
            "gold": {"total": 300},
            "maps": {"11": True},
            "stats": {},
        },
        "1026": {
            "name": "Blasting Wand",
            "gold": {"total": 850},
            "maps": {"11": True},
            "stats": {"FlatMagicDamageMod": 45, "UnknownRiotStat": 1.0},
        },
    },
}
