#!/usr/bin/env python3
"""Fetch Data Dragon snapshot, normalize, optionally write canonical data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from LoLPerfmon.data.loaders import data_root_default
from LoLPerfmon.ingest.normalizer import ddragon_item_to_record
from LoLPerfmon.ingest.reconcile import compute_discrepancies
from LoLPerfmon.ingest.sources import fetch_ddragon_item_raw, latest_ddragon_patch
from LoLPerfmon.ingest.updater import write_data_bundle


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
    normalized: dict[str, dict] = {}
    for iid, entry in data_obj.items():
        if not isinstance(entry, dict):
            continue
        normalized[str(iid)] = ddragon_item_to_record(str(iid), entry)
    current: dict[str, dict] = {}
    items_dir = root / "items"
    if items_dir.is_dir():
        for p in items_dir.glob("*.json"):
            try:
                current[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
    disc = compute_discrepancies(current, {k: normalized[k] for k in normalized if k in current}, source_name="ddragon")
    if args.out_diff:
        args.out_diff.parent.mkdir(parents=True, exist_ok=True)
        args.out_diff.write_text(
            json.dumps([d.__dict__ for d in disc], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    dry = args.dry_run or not args.write_canonical
    rep = write_data_bundle(root, normalized, patch=patch, dry_run=dry)
    print(f"patch={patch} dry_run={dry} canonical_written={not dry} wrote_paths={len(rep.wrote_paths)} discrepancies={len(disc)}")


if __name__ == "__main__":
    main()
