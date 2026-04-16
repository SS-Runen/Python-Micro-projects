from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from typing import Any


def fetch_wiki_html(url: str, *, timeout: float = 30.0) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "LoLPerfmon-ingest/0.1 (educational; +https://example.invalid)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_champion_list_links(html_text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in re.finditer(
        r'href="(/wiki/([^"/#]+)/LoL)"[^>]*title="([^"]+)"',
        html_text,
    ):
        href, slug, title = m.group(1), m.group(2), m.group(3)
        if "List_of" in title or "Champion" in title and "skin" in title.lower():
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
    return uniq[:200]


def wiki_champion_stub(slug: str) -> dict[str, Any]:
    return {"wiki_slug": slug, "source": "wiki_stub", "parsed": False}
