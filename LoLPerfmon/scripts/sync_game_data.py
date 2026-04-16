#!/usr/bin/env python3
"""Fetch Data Dragon snapshot, normalize, optionally write canonical data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from LoLPerfmon.data.loaders import data_root_default
from LoLPerfmon.ingest.normalizer import merge_item_wiki_ddragon_allowlist
from LoLPerfmon.ingest.reconcile import compute_discrepancies
from LoLPerfmon.ingest.sources import fetch_ddragon_item_raw, latest_ddragon_patch
from LoLPerfmon.ingest.updater import write_data_bundle
from LoLPerfmon.ingest.wiki_items import LIST_OF_ITEMS_URL, try_wiki_sr_allowlist


def main() -> None:
    p = argparse.ArgumentParser(description="Sync normalized item data from Data Dragon.")
    p.add_argument("--patch", type=str, default="", help="Data Dragon patch version")
    p.add_argument("--dry-run", action="store_true", help="Do not write canonical files")
    p.add_argument(
        "--write-canonical",
        action="store_true",
        help="Write all normalized items to data/items (large). Default: raw snapshot + diff only.",
    )
    p.add_argument("--out-diff", type=Path, default=None, help="Write discrepancy JSON path")
    p.add_argument("--data-root", type=Path, default=None)
    p.add_argument("--skip-wiki", action="store_true", help="Use full Data Dragon item set (no Wiki SR allowlist)")
    p.add_argument("--wiki-url", type=str, default="", help="Override List of items page URL")
    p.add_argument(
        "--save-wiki-html",
        action="store_true",
        help="Write fetched Wiki HTML under data/raw/wiki/list_of_items.html",
    )
    args = p.parse_args()
    root = args.data_root or data_root_default()
    patch = args.patch or latest_ddragon_patch()
    if not patch:
        print("Could not resolve patch version", file=sys.stderr)
        sys.exit(1)
    raw = fetch_ddragon_item_raw(patch)
    raw_dir = root / "raw" / "ddragon" / patch
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "item.json").write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8")
    data_obj = raw.get("data") or {}
    if not isinstance(data_obj, dict):
        print("Invalid item.json data", file=sys.stderr)
        sys.exit(1)

    wiki_url = (args.wiki_url or "").strip() or LIST_OF_ITEMS_URL
    step = try_wiki_sr_allowlist(skip_wiki=args.skip_wiki, list_url=wiki_url)
    wiki_allowlist = step.allowlist_normalized
    wiki_ok = step.wiki_ok
    wiki_fallback = step.wiki_fallback
    wiki_html_snapshot = ""
    wiki_parse_meta: dict = {}
    if args.skip_wiki:
        print("Skipping Wiki (--skip-wiki); using full Data Dragon item set", file=sys.stderr)
    elif not step.wiki_ok and step.wiki_fallback and step.last_error:
        print(f"Wiki fetch/parse failed, using Data Dragon only: {step.last_error}", file=sys.stderr)
    if step.wiki_ok:
        wiki_parse_meta = {
            "entries_parsed": step.entries_parsed,
            "excluded_by_section": step.excluded_by_section,
            "excluded_by_mode": step.excluded_by_mode,
        }
    if step.wiki_html and args.save_wiki_html:
        wdir = root / "raw" / "wiki"
        wdir.mkdir(parents=True, exist_ok=True)
        wh = wdir / "list_of_items.html"
        wh.write_text(step.wiki_html, encoding="utf-8")
        wiki_html_snapshot = str(wh)

    normalized, wiki_disc = merge_item_wiki_ddragon_allowlist(
        data_obj,
        wiki_allowlist,
        wiki_ok=wiki_ok,
        wiki_fallback=wiki_fallback,
        patch=patch,
        wiki_list_url=wiki_url,
    )
    current: dict[str, dict] = {}
    items_dir = root / "items"
    if items_dir.is_dir():
        for p in items_dir.glob("*.json"):
            try:
                current[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
    disc = compute_discrepancies(current, {k: normalized[k] for k in normalized if k in current}, source_name="ddragon")
    all_disc = list(disc) + list(wiki_disc)
    manifest_extra = {
        "wiki_sync": {
            "wiki_ok": wiki_ok,
            "wiki_fallback": wiki_fallback,
            "wiki_list_url": wiki_url,
            "wiki_html_snapshot": wiki_html_snapshot,
            "allowlist_size": len(wiki_allowlist) if wiki_allowlist is not None else None,
            "ddragon_item_count": len([k for k, v in data_obj.items() if isinstance(v, dict)]),
            "included_after_join": len(normalized),
            **wiki_parse_meta,
        }
    }
    if args.out_diff:
        args.out_diff.parent.mkdir(parents=True, exist_ok=True)
        args.out_diff.write_text(
            json.dumps([d.__dict__ for d in all_disc], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    dry = args.dry_run or not args.write_canonical
    rep = write_data_bundle(root, normalized, patch=patch, dry_run=dry, manifest_extra=manifest_extra)
    print(
        f"patch={patch} dry_run={dry} canonical_written={not dry} wrote_paths={len(rep.wrote_paths)} "
        f"discrepancies={len(all_disc)} wiki_fallback={wiki_fallback}"
    )


if __name__ == "__main__":
    main()
