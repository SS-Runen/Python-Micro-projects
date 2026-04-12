"""
Fetch champion and item definitions from Riot **Data Dragon** (CDN JSON over HTTPS).

This is **not** the Riot Games API: requests go to ``ddragon.leagueoflegends.com`` only.
Per Riot's docs (`Data Dragon` under https://developer.riotgames.com/docs/lol ), these are
static data files; **no** ``RGAPI-`` / developer API key is used or required here. API keys
apply to ``*.api.riotgames.com`` endpoints (match history, summoners, etc.), which this
module does not call.

Falls back to None on network/parse errors so callers can use offline bundles.

Champion filenames on the CDN use the ``id`` field from each champion summary (see
``champion.json``); display names differ (e.g. Wukong → ``MonkeyKing``). Per-champion
JSON is fetched after resolving the caller’s string against the patch’s champion list.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .ddragon_spell_parse import kit_params_from_spells, parse_champion_spells
from .models import ChampionProfile, ItemDef, StatBonus

DDRAGON_VERSIONS = "https://ddragon.leagueoflegends.com/api/versions.json"
USER_AGENT = "LoLPerfmonSim/1.0 (educational; +https://github.com)"

# Per-patch champion list (``champion.json``) — one fetch per version for id/name resolution.
_champion_index_cache: dict[str, "ChampionDDragonIndex | None"] = {}

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


def _alnum_lower(s: str) -> str:
    return "".join(c.lower() for c in s if c.isalnum())


@dataclass
class ChampionDDragonIndex:
    """
    Maps user input to the Data Dragon **champion id** string used in
    ``/cdn/<version>/data/<lang>/champion/<id>.json`` (e.g. ``MonkeyKing`` for Wukong).

    Built from ``champion.json`` ``data`` entries: each summary has ``id`` (filename) and
    ``name`` (display name); see Riot Data Dragon docs.
    """

    lower_to_id: dict[str, str] = field(default_factory=dict)

    def resolve(self, user: str) -> str | None:
        s = user.strip()
        if not s:
            return None
        low = s.lower()
        if low in self.lower_to_id:
            return self.lower_to_id[low]
        compact = _alnum_lower(s)
        if compact in self.lower_to_id:
            return self.lower_to_id[compact]
        return None


def champion_list_json(version: str, timeout: float = 25.0) -> dict[str, Any] | None:
    """Full champion list (summaries only) — used to resolve internal ids vs display names."""
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
    try:
        data = _get_json(url, timeout=timeout)
        return data if isinstance(data, dict) else None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None


def champion_index_from_list_payload(payload: dict[str, Any]) -> ChampionDDragonIndex:
    """Pure: build resolver from a ``champion.json``-shaped dict (for unit tests)."""
    m: dict[str, str] = {}
    champions = payload.get("data") or {}
    if not isinstance(champions, dict):
        return ChampionDDragonIndex(lower_to_id=m)
    for _k, summary in champions.items():
        if not isinstance(summary, dict):
            continue
        did = str(summary.get("id", "") or _k).strip()
        if not did:
            continue
        name = str(summary.get("name", "") or "").strip()
        aliases: set[str] = set()
        aliases.add(did.lower())
        aliases.add(_alnum_lower(did))
        if name:
            aliases.add(name.lower())
            aliases.add(_alnum_lower(name))
        for a in aliases:
            if a and a not in m:
                m[a] = did
    return ChampionDDragonIndex(lower_to_id=m)


def champion_index_for_version(version: str, timeout: float = 25.0) -> ChampionDDragonIndex | None:
    """Cached index for a patch; returns None if ``champion.json`` cannot be loaded (not cached)."""
    if version in _champion_index_cache:
        return _champion_index_cache[version]
    raw = champion_list_json(version, timeout=timeout)
    if not raw:
        return None
    idx = champion_index_from_list_payload(raw)
    _champion_index_cache[version] = idx
    return idx


def clear_champion_index_cache() -> None:
    """Test hook: reset cached indices (e.g. after monkeypatching fetch)."""
    _champion_index_cache.clear()


def latest_version(timeout: float = 15.0) -> str | None:
    try:
        data = _get_json(DDRAGON_VERSIONS, timeout=timeout)
        if isinstance(data, list) and data:
            return str(data[0])
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None
    return None


def champion_json(version: str, champion_id: str, timeout: float = 20.0) -> dict[str, Any] | None:
    """
    Load one champion's full JSON. ``champion_id`` may be a Data Dragon id (``Lux``),
    display name (``Wukong``), or compact spelling (``kaisa``); resolution uses
    ``champion.json`` for the given ``version``. If the index loads but the name is
    unknown, returns None. If the index cannot be loaded, falls back to ``capitalize()``
    for the filename (works for simple ids like ``lux`` only).
    """
    s = champion_id.strip()
    if not s:
        return None
    resolved: str | None = None
    idx = champion_index_for_version(version, timeout=timeout)
    if idx is not None:
        resolved = idx.resolve(champion_id)
        if resolved is None:
            return None
    else:
        resolved = s.capitalize()
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion/{resolved}.json"
    try:
        data = _get_json(url, timeout=timeout)
        inner = data.get("data", {}) if isinstance(data, dict) else {}
        if not isinstance(inner, dict):
            return None
        return inner.get(resolved)
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
    spell_data = parse_champion_spells(champion_key, raw)
    kit = kit_params_from_spells(champion_key, spell_data)
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


def fetch_champion_jsons(version: str, keys: tuple[str, ...], timeout: float = 20.0) -> dict[str, dict[str, Any]]:
    """Raw Data Dragon champion payloads keyed by lower-case id (for audits and parsers)."""
    out: dict[str, dict[str, Any]] = {}
    for k in keys:
        raw = champion_json(version, k, timeout=timeout)
        if raw:
            out[k.lower()] = raw
    return out


def summoners_rift_item_defs_all(item_data: dict[str, Any]) -> dict[str, ItemDef]:
    """Every Summoner's Rift (maps[\"11\"]) item in one O(n) pass over ``item.json`` ``data``."""
    out: dict[str, ItemDef] = {}
    raw_by_id: dict[str, dict[str, Any]] = item_data.get("data") or {}
    for sid, raw in raw_by_id.items():
        if not isinstance(raw, dict):
            continue
        ent = item_def_from_ddragon_entry(str(sid), raw)
        if ent:
            out[ent.id] = ent
    return out


def items_for_sim_from_item_data(item_data: dict[str, Any]) -> dict[str, ItemDef]:
    """Recipe closure from name seeds — same as :func:`fetch_items_for_sim` but uses preloaded JSON."""
    seeds = find_items_by_name_substring(
        item_data,
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
    return recipe_closure_from_seeds(item_data, set(seeds.keys()))


def champions_from_raw(raw_by_id: dict[str, dict[str, Any]]) -> dict[str, ChampionProfile]:
    """Build profiles from pre-fetched Data Dragon payloads (one network round-trip)."""
    return {cid: champion_profile_from_ddragon(cid, raw) for cid, raw in raw_by_id.items()}


def fetch_champions(version: str, keys: tuple[str, ...], timeout: float = 20.0) -> dict[str, ChampionProfile]:
    return champions_from_raw(fetch_champion_jsons(version, keys, timeout=timeout))


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
    return items_for_sim_from_item_data(full)
