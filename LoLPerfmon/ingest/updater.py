from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from LoLPerfmon.ingest.provenance import checksum_json, utc_timestamp


@dataclass(frozen=True)
class WriteReport:
    wrote_paths: tuple[Path, ...]
    dry_run: bool
    manifest_checksum: str


def write_json(path: Path, obj: Any, *, dry_run: bool) -> bool:
    if dry_run:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def write_data_bundle(
    data_root: Path,
    items_by_id: dict[str, dict[str, Any]],
    *,
    patch: str,
    dry_run: bool = False,
) -> WriteReport:
    wrote: list[Path] = []
    items_dir = data_root / "items"
    for iid, rec in items_by_id.items():
        p = items_dir / f"{iid}.json"
        if write_json(p, rec, dry_run=dry_run):
            wrote.append(p)
    manifest = {
        "schema_version": "1",
        "patch_version": patch,
        "sources": [{"name": "ddragon_normalized", "fetched_at": utc_timestamp()}],
        "checksums": {"items": checksum_json(items_by_id)},
    }
    mp = data_root / "manifest" / "data_manifest.json"
    if write_json(mp, manifest, dry_run=dry_run):
        wrote.append(mp)
    return WriteReport(wrote_paths=tuple(wrote), dry_run=dry_run, manifest_checksum=manifest["checksums"]["items"])
