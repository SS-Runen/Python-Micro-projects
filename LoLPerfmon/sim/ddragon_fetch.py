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
    name = str(raw.get("name", item_id))
    stats_raw = raw.get("stats") or {}
    stats_f = {k: float(v) for k, v in stats_raw.items() if isinstance(v, (int, float))}
    bonus = _bonus_from_item_stats(stats_f)
    return ItemDef(id=str(item_id), name=name, total_cost=float(total), stats=bonus)


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


def fetch_items_for_sim(version: str, timeout: float = 30.0) -> dict[str, ItemDef]:
    full = item_json_full(version, timeout=timeout)
    if not full:
        return {}
    items = find_items_by_name_substring(full, "Doran", "Recurve", "Needlessly", "Lost Chapter", "B. F.")
    return items
