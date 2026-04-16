from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from LoLPerfmon.ingest.normalizer import (
    ddragon_champion_to_record,
    merge_champion_wiki_ddragon,
)
from LoLPerfmon.ingest.sources import (
    ddragon_champion_full_url,
    fetch_ddragon_champion_full_raw,
    fetch_ddragon_champion_index_raw,
    latest_ddragon_patch,
    resolve_ddragon_champion_key,
)
from LoLPerfmon.ingest.wiki_parser import (
    LIST_OF_CHAMPIONS_URL,
    ChampionListEntry,
    fetch_champion_detail_html,
    fetch_wiki_html,
    normalize_champion_id,
    parse_champion_list_table,
    parse_wiki_champion_detail_stats,
)
from LoLPerfmon.ingest.updater import write_json


def _find_list_entry(entries: list[ChampionListEntry], champion_id: str) -> ChampionListEntry | None:
    target = normalize_champion_id(champion_id)
    for e in entries:
        if e.champion_id == target:
            return e
    return None


def build_champion_record(
    champion_id: str,
    *,
    patch: str | None = None,
    list_html: str | None = None,
    list_entry: ChampionListEntry | None = None,
    wiki_detail_html: str | None = None,
    champion_index: dict[str, Any] | None = None,
    full_champion_json: dict[str, Any] | None = None,
    prefer_dd_on_conflict: bool = False,
    save_raw_dir: Path | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Assemble a champion JSON dict: Data Dragon base, Wiki stats overlay when parseable."""
    patch_resolved = patch or latest_ddragon_patch(timeout=timeout)
    if not patch_resolved:
        raise RuntimeError("Could not resolve Data Dragon patch version")
    patch = patch_resolved

    idx = champion_index if champion_index is not None else fetch_ddragon_champion_index_raw(patch, timeout=timeout)
    dkey = resolve_ddragon_champion_key(idx, champion_id)
    if not dkey:
        raise KeyError(f"No Data Dragon entry for champion_id={champion_id!r}")

    full = full_champion_json if full_champion_json is not None else fetch_ddragon_champion_full_raw(patch, dkey, timeout=timeout)
    src_url = ddragon_champion_full_url(patch, dkey)
    dd_rec = ddragon_champion_to_record(full, dkey, patch=patch, source_url=src_url)

    wiki_partial: dict[str, Any] | None = None
    if wiki_detail_html is not None:
        wiki_partial = parse_wiki_champion_detail_stats(wiki_detail_html) or None
    else:
        list_src = list_html if list_html is not None else fetch_wiki_html(LIST_OF_CHAMPIONS_URL, timeout=timeout)
        if save_raw_dir is not None:
            save_raw_dir.mkdir(parents=True, exist_ok=True)
            (save_raw_dir / "list_of_champions.html").write_text(list_src, encoding="utf-8")
        entry = list_entry
        if entry is None:
            entries = parse_champion_list_table(list_src)
            entry = _find_list_entry(entries, champion_id)
        wiki_href: str | None = entry.wiki_href if entry else f"/wiki/{dkey}/LoL"
        detail = fetch_champion_detail_html(wiki_href, timeout=timeout)
        if save_raw_dir is not None:
            safe = normalize_champion_id(champion_id) or "unknown"
            (save_raw_dir / f"champion_{safe}_lol.html").write_text(detail, encoding="utf-8")
        wiki_partial = parse_wiki_champion_detail_stats(detail) or None

    merged, _ = merge_champion_wiki_ddragon(
        dd_rec,
        wiki_partial,
        prefer_dd_on_conflict=prefer_dd_on_conflict,
    )
    return merged


def sync_champion_to_disk(
    data_root: Path,
    champion_id: str,
    *,
    patch: str | None = None,
    list_html: str | None = None,
    list_entry: ChampionListEntry | None = None,
    wiki_detail_html: str | None = None,
    champion_index: dict[str, Any] | None = None,
    full_champion_json: dict[str, Any] | None = None,
    prefer_dd_on_conflict: bool = False,
    save_raw_dir: Path | None = None,
    dry_run: bool = False,
    timeout: float = 30.0,
) -> Path | None:
    rec = build_champion_record(
        champion_id,
        patch=patch,
        list_html=list_html,
        list_entry=list_entry,
        wiki_detail_html=wiki_detail_html,
        champion_index=champion_index,
        full_champion_json=full_champion_json,
        prefer_dd_on_conflict=prefer_dd_on_conflict,
        save_raw_dir=save_raw_dir,
        timeout=timeout,
    )
    cid = str(rec.get("champion_id", normalize_champion_id(champion_id)))
    out = data_root / "champions" / f"{cid}.json"
    if write_json(out, rec, dry_run=dry_run):
        return out
    return None


def sync_all_champions_to_disk(
    data_root: Path,
    *,
    patch: str | None = None,
    list_html: str | None = None,
    prefer_dd_on_conflict: bool = False,
    save_raw_dir: Path | None = None,
    dry_run: bool = False,
    timeout: float = 30.0,
) -> tuple[list[Path], list[str]]:
    """Sync every champion discovered from ``table#tpt-champions`` (network-heavy)."""
    patch_resolved = patch or latest_ddragon_patch(timeout=timeout)
    if not patch_resolved:
        raise RuntimeError("Could not resolve Data Dragon patch version")
    patch = patch_resolved
    list_src = list_html if list_html is not None else fetch_wiki_html(LIST_OF_CHAMPIONS_URL, timeout=timeout)
    if save_raw_dir is not None:
        save_raw_dir.mkdir(parents=True, exist_ok=True)
        (save_raw_dir / "list_of_champions.html").write_text(list_src, encoding="utf-8")
    entries = parse_champion_list_table(list_src)
    idx = fetch_ddragon_champion_index_raw(patch, timeout=timeout)
    wrote: list[Path] = []
    errors: list[str] = []
    for e in entries:
        try:
            p = sync_champion_to_disk(
                data_root,
                e.champion_id,
                patch=patch,
                list_html=list_src,
                list_entry=e,
                champion_index=idx,
                prefer_dd_on_conflict=prefer_dd_on_conflict,
                save_raw_dir=save_raw_dir,
                dry_run=dry_run,
                timeout=timeout,
            )
            if p:
                wrote.append(p)
        except (OSError, KeyError, RuntimeError, ValueError, json.JSONDecodeError) as ex:
            errors.append(f"{e.champion_id}: {ex}")
    return wrote, errors
