from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"


def fetch_json(url: str, *, timeout: float = 30.0) -> Any:
    req = urllib.request.Request(url, headers={"Accept-Charset": "utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def latest_ddragon_patch(timeout: float = 30.0) -> str | None:
    try:
        versions = fetch_json(VERSIONS_URL, timeout=timeout)
        if isinstance(versions, list) and versions:
            return str(versions[0])
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return None
    return None


def ddragon_item_url(patch: str, lang: str = "en_US") -> str:
    return f"http://ddragon.leagueoflegends.com/cdn/{patch}/data/{lang}/item.json"


def ddragon_champion_list_url(patch: str, lang: str = "en_US") -> str:
    return f"http://ddragon.leagueoflegends.com/cdn/{patch}/data/{lang}/champion.json"


def fetch_ddragon_item_raw(patch: str, *, timeout: float = 30.0) -> dict[str, Any]:
    url = ddragon_item_url(patch)
    data = fetch_json(url, timeout=timeout)
    if not isinstance(data, dict):
        raise ValueError("unexpected item.json shape")
    return data


def fetch_ddragon_champion_index_raw(patch: str, *, timeout: float = 30.0) -> dict[str, Any]:
    url = ddragon_champion_list_url(patch)
    data = fetch_json(url, timeout=timeout)
    if not isinstance(data, dict):
        raise ValueError("unexpected champion.json shape")
    return data


def ddragon_champion_full_url(patch: str, champion_key: str, lang: str = "en_US") -> str:
    return f"http://ddragon.leagueoflegends.com/cdn/{patch}/data/{lang}/champion/{champion_key}.json"


def fetch_ddragon_champion_full_raw(
    patch: str,
    champion_key: str,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    url = ddragon_champion_full_url(patch, champion_key)
    data = fetch_json(url, timeout=timeout)
    if not isinstance(data, dict):
        raise ValueError("unexpected per-champion champion JSON shape")
    return data


def resolve_ddragon_champion_key(champion_index: dict[str, Any], champion_id: str) -> str | None:
    """Map normalized champion id (e.g. ``lux``, ``leesin``) to Data Dragon data key (e.g. ``Lux``)."""
    from LoLPerfmon.ingest.wiki_parser import normalize_champion_id

    target = normalize_champion_id(champion_id)
    data = champion_index.get("data") or {}
    if not isinstance(data, dict):
        return None
    for key, val in data.items():
        if not isinstance(val, dict):
            continue
        rid = normalize_champion_id(str(val.get("id", key)))
        if rid == target:
            return str(key)
    return None
