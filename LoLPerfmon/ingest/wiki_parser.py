from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


WIKI_BASE = "https://leagueoflegends.fandom.com"
LIST_OF_CHAMPIONS_URL = f"{WIKI_BASE}/wiki/List_of_champions"


def fetch_wiki_html(url: str, *, timeout: float = 30.0) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "LoLPerfmon-ingest/0.1 (educational; +https://example.invalid)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def wiki_page_url(wiki_path: str) -> str:
    path = wiki_path if wiki_path.startswith("/") else f"/{wiki_path}"
    return f"{WIKI_BASE}{path}"


@dataclass(frozen=True)
class ChampionListEntry:
    """One row from table#tpt-champions."""

    display_name: str
    wiki_href: str
    wiki_slug: str

    @property
    def champion_id(self) -> str:
        return wiki_slug_to_champion_id(self.wiki_slug)


def normalize_champion_id(raw: str) -> str:
    """Match DDragon ``id`` style: lowercase alnum only (e.g. ``LeeSin`` → ``leesin``)."""
    return re.sub(r"[^a-z0-9]", "", raw.lower())


def wiki_slug_to_champion_id(wiki_slug: str) -> str:
    return normalize_champion_id(wiki_slug.replace(" ", "_"))


def _strip_tags(fragment: str) -> str:
    return re.sub(r"<[^>]+>", " ", fragment)


def parse_champion_list_links(html_text: str) -> list[tuple[str, str]]:
    """Legacy regex-based list (kept for tests); prefer :func:`parse_champion_list_table`."""
    out: list[tuple[str, str]] = []
    for m in re.finditer(
        r'href="(/wiki/([^"/#]+)/LoL)"[^>]*title="([^"]+)"',
        html_text,
    ):
        href, slug, title = m.group(1), m.group(2), m.group(3)
        if "List_of" in title or ("Champion" in title and "skin" in title.lower()):
            continue
        out.append((html.unescape(href), html.unescape(slug)))
    seen: set[str] = set()
    uniq: list[tuple[str, str]] = []
    for h, s in out:
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append((h, s))
    return uniq


def parse_champion_list_table(html_text: str) -> list[ChampionListEntry]:
    """Parse ``table#tpt-champions``: champion name, Wiki path ``/wiki/{Slug}/LoL``.

    Skips rows without a real ``/wiki/.../LoL`` link (placeholders, uploads, redlinks).
    """
    m = re.search(
        r'<table[^>]*\bid=["\']tpt-champions["\'][^>]*>(.*?)</table>',
        html_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return []
    table_inner = m.group(1)
    rows: list[ChampionListEntry] = []
    seen_slugs: set[str] = set()

    for rm in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", table_inner, flags=re.DOTALL | re.IGNORECASE):
        row = rm.group(1)
        link_m = re.search(
            r'<a\s+[^>]*\bhref="(/wiki/[^"]+/LoL)"',
            row,
            flags=re.IGNORECASE,
        )
        if not link_m:
            continue
        href = html.unescape(link_m.group(1))
        if "Special:" in href or "action=edit" in href:
            continue
        slug_m = re.search(r"/wiki/([^/]+)/LoL", href)
        if not slug_m:
            continue
        wiki_slug = html.unescape(slug_m.group(1))
        wiki_slug = urllib.parse.unquote(wiki_slug)
        if not wiki_slug or wiki_slug.startswith("File:"):
            continue

        name_m = re.search(
            r'data-sort-value="([^"]+)"',
            row,
        )
        display_name = html.unescape(name_m.group(1)) if name_m else wiki_slug.replace("_", " ")

        key = wiki_slug.lower()
        if key in seen_slugs:
            continue
        seen_slugs.add(key)
        rows.append(ChampionListEntry(display_name=display_name, wiki_href=href, wiki_slug=wiki_slug))

    return rows


def fetch_champion_detail_html(wiki_href: str, *, timeout: float = 30.0) -> str:
    """GET a champion ``/wiki/.../LoL`` page (``wiki_href`` starts with ``/wiki/``)."""
    return fetch_wiki_html(wiki_page_url(wiki_href), timeout=timeout)


def wiki_champion_stub(slug: str) -> dict[str, Any]:
    return {"wiki_slug": slug, "source": "wiki_stub", "parsed": False}


_AD_ROW = re.compile(
    r"Attack\s+damage[^0-9]{0,80}?([\d.]+)\s*\(\s*\+\s*([\d.]+)\s*\)",
    re.IGNORECASE | re.DOTALL,
)
_AS_ROW = re.compile(
    r"Attack\s+speed[^0-9]{0,80}?([\d.]+)\s*\(\s*\+\s*([\d.]+)\s*%?\s*\)",
    re.IGNORECASE | re.DOTALL,
)
_AP_ROW = re.compile(
    r"(?:Ability\s+power|Magic\s+damage)[^0-9]{0,80}?([\d.]+)\s*\(\s*\+\s*([\d.]+)\s*\)",
    re.IGNORECASE | re.DOTALL,
)


def parse_wiki_champion_detail_stats(html_text: str) -> dict[str, Any]:
    """Best-effort parse of rendered champion /LoL page for level-1 stats.

    Returns keys ``base_stats_at_level1``, ``growth_per_level`` (partial), and
    ``parsed_fields`` when any stat was found. Empty dict if nothing usable.
    """
    text = _strip_tags(html_text)
    text = re.sub(r"\s+", " ", text)
    base: dict[str, float] = {}
    growth: dict[str, float] = {}
    parsed: list[str] = []

    m = _AD_ROW.search(text)
    if m:
        base["attack_damage"] = float(m.group(1))
        growth["attack_damage"] = float(m.group(2))
        parsed.append("attack_damage")

    m = _AS_ROW.search(text)
    if m:
        base["attack_speed"] = float(m.group(1))
        g = float(m.group(2))
        growth["attack_speed"] = g / 100.0 if g > 1.0 else g
        parsed.append("attack_speed")

    m = _AP_ROW.search(text)
    if m:
        base["ability_power"] = float(m.group(1))
        growth["ability_power"] = float(m.group(2))
        parsed.append("ability_power")

    if not base:
        return {}
    for k in ("ability_power",):
        base.setdefault(k, 0.0)
        growth.setdefault(k, 0.0)
    base.setdefault("attack_speed", 0.625)
    growth.setdefault("attack_speed", 0.0)

    return {
        "base_stats_at_level1": base,
        "growth_per_level": growth,
        "parsed_fields": parsed,
    }
