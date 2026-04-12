"""
Fetch champion and item definitions from Riot Data Dragon (HTTPS, no API key).

Falls back to None on network/parse errors so callers can use offline bundles.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .models import ChampionProfile, ItemDef, KitParams, StatBonus

DDRAGON_VERSIONS = "https://ddragon.leagueoflegends.com/api/versions.json"
USER_AGENT = "LoLPerfmonSim/1.0 (educational; +https://github.com)"

# Riot item.json ``maps`` field: ``"11"`` = Summoner's Rift (aligns with wiki "Classic SR 5v5" filter).
SUMMONERS_RIFT_CLASSIC_MAP_ID = "11"


def item_on_summoners_rift_classic(raw: dict[str, Any]) -> bool:
    """
    True if the item is available on Summoner's Rift classic 5v5 per Data Dragon.

    This matches the League of Legends wiki list when the game-mode dropdown is set to
    "Classic SR 5v5" (option value ``classic sr 5v5`` on the Item page); we use Riot's
    authoritative ``maps`` data instead of scraping HTML.
    """
    m = raw.get("maps")
    if not isinstance(m, dict):
        return False
    return m.get(SUMMONERS_RIFT_CLASSIC_MAP_ID) is True


def _get_json(url: str, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def latest_version(timeout: float = 15.0) -> str | None:
    try:
        data = _get_json(DDRAGON_VERSIONS, timeout=timeout)
        if isinstance(data, list) and data:
            return str(data[0])
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None
    return None


def champion_json(version: str, champion_id: str, timeout: float = 20.0) -> dict[str, Any] | None:
    key = champion_id.capitalize()
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion/{key}.json"
    try:
        data = _get_json(url, timeout=timeout)
        return data.get("data", {}).get(key)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError, KeyError):
        return None


def item_json_full(version: str, timeout: float = 30.0) -> dict[str, Any] | None:
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/item.json"
    try:
        return _get_json(url, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None


def _bonus_from_item_stats(stats: dict[str, float]) -> StatBonus:
    return StatBonus(
        attack_damage=float(stats.get("FlatPhysicalDamageMod", 0) or 0),
        ability_power=float(stats.get("FlatMagicDamageMod", 0) or 0),
        bonus_attack_speed_fraction=float(stats.get("PercentAttackSpeedMod", 0) or 0) / 100.0
        if stats.get("PercentAttackSpeedMod")
        else 0.0,
        ability_haste=float(stats.get("FlatHasteMod", 0) or stats.get("FlatAbilityHasteMod", 0) or 0),
        health=float(stats.get("FlatHPPoolMod", 0) or 0),
        mana=float(stats.get("FlatMPPoolMod", 0) or 0),
        armor=float(stats.get("FlatArmorMod", 0) or 0),
        magic_resist=float(stats.get("FlatSpellBlockMod", 0) or 0),
    )


def item_def_from_ddragon_entry(item_id: str, raw: dict[str, Any]) -> ItemDef | None:
    gold = raw.get("gold") or {}
    total = gold.get("total")
    if total is None:
        return None
    if not item_on_summoners_rift_classic(raw):
        return None
    name = str(raw.get("name", item_id))
    stats_raw = raw.get("stats") or {}
    stats_f = {k: float(v) for k, v in stats_raw.items() if isinstance(v, (int, float))}
    bonus = _bonus_from_item_stats(stats_f)
    from_raw = raw.get("from") or []
    from_ids = tuple(str(x) for x in from_raw) if isinstance(from_raw, list) else ()
    return ItemDef(
        id=str(item_id),
        name=name,
        total_cost=float(total),
        stats=bonus,
        from_ids=from_ids,
    )


def find_items_by_name_substring(item_data: dict[str, Any], *substrings: str) -> dict[str, ItemDef]:
    out: dict[str, ItemDef] = {}
    items = item_data.get("data") or {}
    for sid, raw in items.items():
        name = str(raw.get("name", ""))
        if any(s.lower() in name.lower() for s in substrings):
            ent = item_def_from_ddragon_entry(sid, raw)
            if ent:
                out[ent.id] = ent
    return out


def champion_profile_from_ddragon(champion_key: str, raw: dict[str, Any]) -> ChampionProfile:
    s = raw.get("stats") or {}
    hp = float(s.get("hp", 580))
    hppl = float(s.get("hpperlevel", 90))
    mp = float(s.get("mp", 400))
    mppl = float(s.get("mpperlevel", 25))
    ad = float(s.get("attackdamage", 55))
    adpl = float(s.get("attackdamageperlevel", 3))
    ar = float(s.get("armor", 25))
    arpl = float(s.get("armorperlevel", 4))
    mr = float(s.get("spellblock", 30))
    mrpl = float(s.get("spellblockperlevel", 1.25))
    base_as = float(s.get("attackspeed", 0.625))
    aspl = float(s.get("attackspeedperlevel", 0.0))
    as_ratio = 0.625
    bonus_as_growth = aspl / 100.0 if aspl > 0.5 else 0.03
    kit = KitParams(ad_weight=0.3, ap_weight=1.0, as_weight=0.2, ah_weight=0.02, base_ability_dps=12.0)
    cid = champion_key.lower()
    return ChampionProfile(
        id=cid,
        base_health=hp,
        growth_health=hppl,
        base_mana=mp,
        growth_mana=mppl,
        base_attack_damage=ad,
        growth_attack_damage=adpl,
        base_ability_power=0.0,
        growth_ability_power=0.0,
        base_armor=ar,
        growth_armor=arpl,
        base_magic_resist=mr,
        growth_magic_resist=mrpl,
        base_attack_speed=base_as,
        attack_speed_ratio=as_ratio,
        bonus_attack_speed_growth=bonus_as_growth,
        kit=kit,
    )


def fetch_champions(version: str, keys: tuple[str, ...], timeout: float = 20.0) -> dict[str, ChampionProfile]:
    out: dict[str, ChampionProfile] = {}
    for k in keys:
        raw = champion_json(version, k, timeout=timeout)
        if raw:
            out[k.lower()] = champion_profile_from_ddragon(k, raw)
    return out


def recipe_closure_from_seeds(item_data: dict[str, Any], seed_ids: set[str]) -> dict[str, ItemDef]:
    """
    Include every Data Dragon item id reachable via ``from`` edges from ``seed_ids`` so
    components and recipe fees are simulated with real costs. Only ids that are enabled on
    Summoner's Rift (``maps["11"]``) are included.
    """
    raw_by_id: dict[str, dict[str, Any]] = item_data.get("data") or {}
    needed: set[str] = set()
    for sid in seed_ids:
        raw = raw_by_id.get(sid)
        if raw and item_on_summoners_rift_classic(raw):
            needed.add(sid)
    changed = True
    while changed:
        changed = False
        for i in list(needed):
            raw = raw_by_id.get(i)
            if not raw:
                continue
            for comp in raw.get("from") or []:
                cid = str(comp)
                craw = raw_by_id.get(cid)
                if craw and item_on_summoners_rift_classic(craw) and cid not in needed:
                    needed.add(cid)
                    changed = True
    out: dict[str, ItemDef] = {}
    for i in needed:
        raw = raw_by_id.get(i)
        if not raw:
            continue
        ent = item_def_from_ddragon_entry(i, raw)
        if ent:
            out[ent.id] = ent
    return out


def fetch_items_for_sim(version: str, timeout: float = 30.0) -> dict[str, ItemDef]:
    full = item_json_full(version, timeout=timeout)
    if not full:
        return {}
    seeds = find_items_by_name_substring(
        full,
        "Doran",
        "Recurve",
        "Needlessly",
        "Lost Chapter",
        "B. F.",
        "Luden",
        "Statikk",
        "Infinity",
    )
    if not seeds:
        return {}
    return recipe_closure_from_seeds(full, set(seeds.keys()))
