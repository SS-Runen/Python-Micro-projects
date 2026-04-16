#!/usr/bin/env python3
"""Dry-run discrepancy audit between on-disk canonical items and Data Dragon."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from LoLPerfmon.data.loaders import data_root_default, load_items_dir
from LoLPerfmon.ingest.normalizer import ddragon_item_to_record
from LoLPerfmon.ingest.reconcile import compute_discrepancies
from LoLPerfmon.ingest.sources import fetch_ddragon_item_raw, latest_ddragon_patch
from LoLPerfmon.ingest.wiki_items import LIST_OF_ITEMS_URL, fetch_wiki_list_of_items_html, normalize_item_display_name, parse_wiki_item_list_grid


def item_to_dict(item) -> dict:
    return {
        "item_id": item.item_id,
        "name": item.name,
        "cost": item.cost,
        "stats_granted": dict(item.stats_granted),
        "passive_tags": list(item.passive_tags),
        "builds_from": list(item.builds_from),
        "builds_into": list(item.builds_into),
        "slot_cost": item.slot_cost,
        "is_jungle_starter": item.is_jungle_starter,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Audit item discrepancies (no writes).")
    p.add_argument("--patch", type=str, default="")
    p.add_argument("--data-root", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--skip-wiki", action="store_true", help="Do not fetch Wiki SR allowlist for extra metrics")
    p.add_argument("--wiki-url", type=str, default="", help="Override List of items page URL")
    p.add_argument(
        "--wiki-html-file",
        type=Path,
        default=None,
        help="Use local HTML instead of fetching (for tests or offline)",
    )
    args = p.parse_args()
    root = args.data_root or data_root_default()
    patch = args.patch or latest_ddragon_patch()
    if not patch:
        print("Could not resolve patch", file=sys.stderr)
        sys.exit(1)
    raw = fetch_ddragon_item_raw(patch)
    data_obj = raw.get("data") or {}
    normalized: dict[str, dict] = {}
    if isinstance(data_obj, dict):
        for iid, entry in data_obj.items():
            if isinstance(entry, dict):
                normalized[str(iid)] = ddragon_item_to_record(str(iid), entry)
    current_items = load_items_dir(root / "items")
    current = {str(k): item_to_dict(v) for k, v in current_items.items()}
    disc = compute_discrepancies(current, normalized, source_name="ddragon")
    high = [d for d in disc if d.severity == "high"]
    if args.out:
        args.out.write_text(json.dumps([d.__dict__ for d in disc], indent=2) + "\n", encoding="utf-8")

    wiki_line = ""
    if not args.skip_wiki:
        try:
            if args.wiki_html_file and args.wiki_html_file.is_file():
                wiki_html = args.wiki_html_file.read_text(encoding="utf-8")
            else:
                wiki_url = (args.wiki_url or "").strip() or LIST_OF_ITEMS_URL
                wiki_html = fetch_wiki_list_of_items_html(wiki_url)
            pr = parse_wiki_item_list_grid(wiki_html)
            allow = pr.allowlist_normalized
            dd_names = {
                normalize_item_display_name(str(v.get("name", "")))
                for v in data_obj.values()
                if isinstance(v, dict)
            }
            dd_names.discard("")
            matched = allow & dd_names
            dd_not_on_wiki_sr = len(dd_names - allow)
            wiki_only = len(allow - dd_names)
            wiki_line = (
                f" wiki_allowlist={len(allow)} ddragon_names={len(dd_names)} "
                f"sr_name_join={len(matched)} ddragon_not_in_wiki_sr={dd_not_on_wiki_sr} wiki_only_no_ddragon_name={wiki_only}"
            )
        except Exception as e:
            wiki_line = f" wiki_metrics_unavailable={e!r}"

    print(
        f"patch={patch} items_local={len(current)} items_ddragon={len(normalized)} discrepancies={len(disc)} high={len(high)}"
        f"{wiki_line}"
    )


if __name__ == "__main__":
    main()
