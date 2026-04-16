#!/usr/bin/env python3
"""Wiki-first champion ingest with Data Dragon fallback: write ``data/champions/<id>.json``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from LoLPerfmon.data.loaders import data_root_default
from LoLPerfmon.ingest.champion_sync import sync_all_champions_to_disk, sync_champion_to_disk


def main() -> None:
    p = argparse.ArgumentParser(description="Sync champion JSON from League Wiki + Data Dragon.")
    p.add_argument("--champion", type=str, default="", help="Champion id (e.g. lux, leesin)")
    p.add_argument("--sync-all-champions", action="store_true", help="Sync every row in table#tpt-champions (slow)")
    p.add_argument("--patch", type=str, default="", help="Data Dragon patch (default: latest)")
    p.add_argument("--dry-run", action="store_true", help="Do not write files")
    p.add_argument(
        "--prefer-dd-on-conflict",
        action="store_true",
        help="Keep Data Dragon numerics when Wiki and DD disagree",
    )
    p.add_argument(
        "--save-raw-wiki",
        action="store_true",
        help="Write fetched HTML under data/raw/wiki/",
    )
    p.add_argument("--data-root", type=Path, default=None)
    args = p.parse_args()
    root = args.data_root or data_root_default()
    patch = args.patch or None
    raw_dir = root / "raw" / "wiki" if args.save_raw_wiki else None

    if args.sync_all_champions:
        wrote, errs = sync_all_champions_to_disk(
            root,
            patch=patch,
            prefer_dd_on_conflict=args.prefer_dd_on_conflict,
            save_raw_dir=raw_dir,
            dry_run=args.dry_run,
        )
        print(f"wrote={len(wrote)} errors={len(errs)}")
        for line in errs[:20]:
            print(line, file=sys.stderr)
        if len(errs) > 20:
            print(f"... and {len(errs) - 20} more errors", file=sys.stderr)
        sys.exit(1 if errs else 0)

    if not args.champion:
        p.error("Pass --champion <id> or --sync-all-champions")
    out = sync_champion_to_disk(
        root,
        args.champion,
        patch=patch,
        prefer_dd_on_conflict=args.prefer_dd_on_conflict,
        save_raw_dir=raw_dir,
        dry_run=args.dry_run,
    )
    if out:
        print(f"wrote {out}")
    elif args.dry_run:
        print("dry-run: no file written")
    else:
        print("failed to write champion file", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
