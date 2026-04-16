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
