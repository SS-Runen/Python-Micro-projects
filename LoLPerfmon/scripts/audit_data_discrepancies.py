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
    print(f"patch={patch} items_local={len(current)} items_ddragon={len(normalized)} discrepancies={len(disc)} high={len(high)}")


if __name__ == "__main__":
    main()
