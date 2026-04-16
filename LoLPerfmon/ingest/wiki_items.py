from __future__ import annotations

import html
import re
import unicodedata
import urllib.request
from dataclasses import dataclass, field

LIST_OF_ITEMS_URL = "https://wiki.leagueoflegends.com/en-us/List_of_items"
CLASSIC_SR_MODE = "classic sr 5v5"

DEFAULT_EXCLUDED_SECTIONS: frozenset[str] = frozenset(
    {
        "Minion and Turret items",
        "Arena Prismatic items",
        "Arena Anvil items",
        "Arena exclusive items",
        "Removed items",
        "Champion exclusive items",
    }
)


def fetch_wiki_list_of_items_html(url: str = LIST_OF_ITEMS_URL, *, timeout: float = 30.0) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "LoLPerfmon-ingest/0.1 (educational)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def normalize_item_display_name(raw: str) -> str:
    s = unicodedata.normalize("NFKC", raw)
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _modes_has_classic_sr(modes_attr: str) -> bool:
    if not modes_attr or not modes_attr.strip():
        return False
    parts = [p.strip().lower() for p in modes_attr.split(",") if p.strip()]
    return CLASSIC_SR_MODE in parts


@dataclass
class WikiItemListEntry:
    display_name: str
    wiki_href: str | None
    modes_raw: str
    section: str


@dataclass
class WikiItemListParseResult:
    allowlist_normalized: set[str]
    entries: list[WikiItemListEntry] = field(default_factory=list)
    excluded_by_section: int = 0
    excluded_by_mode: int = 0


def _section_at_position(section_markers: list[tuple[int, str]], pos: int) -> str:
    current = ""
    for p, name in sorted(section_markers, key=lambda x: x[0]):
        if p > pos:
            break
        current = name
    return current


def parse_wiki_item_list_grid(
    html_text: str,
    *,
    excluded_sections: frozenset[str] | None = None,
) -> WikiItemListParseResult:
    """Parse ``div.item-icon`` rows: ``data-item``, ``data-modes``, optional wiki link.

    Skips icons in *excluded_sections* (nearest preceding ``<dl><dt>``). Keeps only rows
    where *data-modes* lists Classic SR 5v5 (same token as the Wiki filter dropdown).
    """
    excl = excluded_sections if excluded_sections is not None else DEFAULT_EXCLUDED_SECTIONS
    section_markers: list[tuple[int, str]] = []
    for m in re.finditer(
        r"<dl>\s*<dt>\s*([^<]+?)\s*</dt>",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        name = html.unescape(m.group(1)).strip()
        section_markers.append((m.start(), name))

    entries: list[WikiItemListEntry] = []
    excluded_section = 0
    excluded_mode = 0
    allow: set[str] = set()

    for m in re.finditer(r"<div\b[^>]*\bitem-icon\b[^>]*>", html_text, flags=re.IGNORECASE):
        tag = m.group(0)
        dm_item = re.search(r'data-item="([^"]*)"', tag, flags=re.IGNORECASE)
        dm_modes = re.search(r'data-modes="([^"]*)"', tag, flags=re.IGNORECASE)
        if not dm_item:
            continue
        display = html.unescape(dm_item.group(1)).strip()
        modes_raw = dm_modes.group(1) if dm_modes else ""

        href_m = re.search(r'href="(/en-us/[^"]+)"', html_text[m.end() : m.end() + 400], flags=re.IGNORECASE)
        wiki_href = href_m.group(1) if href_m else None

        sec = _section_at_position(section_markers, m.start())
        if sec in excl:
            excluded_section += 1
            continue
        if not _modes_has_classic_sr(modes_raw):
            excluded_mode += 1
            continue

        norm = normalize_item_display_name(display)
        if norm:
            allow.add(norm)
        entries.append(
            WikiItemListEntry(
                display_name=display,
                wiki_href=wiki_href,
                modes_raw=modes_raw,
                section=sec,
            )
        )

    return WikiItemListParseResult(
        allowlist_normalized=allow,
        entries=entries,
        excluded_by_section=excluded_section,
        excluded_by_mode=excluded_mode,
    )


@dataclass
class WikiSrAllowlistStep:
    """Result of fetching/parsing the Wiki List of items for Classic SR allowlisting."""

    allowlist_normalized: set[str] | None
    wiki_ok: bool
    wiki_fallback: bool
    wiki_html: str | None = None
    entries_parsed: int = 0
    excluded_by_section: int = 0
    excluded_by_mode: int = 0
    last_error: str | None = None


def try_wiki_sr_allowlist(*, skip_wiki: bool, list_url: str) -> WikiSrAllowlistStep:
    """Fetch Wiki HTML, parse SR allowlist, or fall back to Data Dragon–only (full item set).

    When *skip_wiki* is True or fetch/parse fails, returns ``wiki_fallback=True`` and
    ``allowlist_normalized=None`` so callers merge the full Data Dragon item table.
    """
    if skip_wiki:
        return WikiSrAllowlistStep(None, False, True, None)
    try:
        wiki_html = fetch_wiki_list_of_items_html(list_url)
        pr = parse_wiki_item_list_grid(wiki_html)
        return WikiSrAllowlistStep(
            set(pr.allowlist_normalized),
            True,
            False,
            wiki_html,
            len(pr.entries),
            pr.excluded_by_section,
            pr.excluded_by_mode,
        )
    except Exception as e:
        return WikiSrAllowlistStep(None, False, True, None, last_error=str(e))
