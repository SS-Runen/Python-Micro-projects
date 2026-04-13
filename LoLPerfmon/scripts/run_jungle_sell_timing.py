#!/usr/bin/env python3
"""Scan greedy jungle farm + optional companion sell times; report best total_farm_gold."""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from LoLPerfmon.sim.bundle_factory import build_offline_bundle, load_ddragon_bundle_with_audit
from LoLPerfmon.sim.ddragon_fetch import latest_version
from LoLPerfmon.sim.jungle_items import jungle_companion_item_ids_sorted, resolve_jungle_starter_item_id
from LoLPerfmon.sim.jungle_sell_timing import optimal_jungle_sell_timing


def main() -> None:
    p = argparse.ArgumentParser(description="Optimal jungle companion sell timing (total_farm_gold)")
    p.add_argument("--champion", type=str, default="karthus")
    p.add_argument("--t-max", type=float, default=3600.0)
    p.add_argument("--jungle-starter", type=str, default="", help="Item id; default = first Jungle-tagged item")
    p.add_argument("--sell-only-after-18", action="store_true")
    p.add_argument("--timeout", type=float, default=45.0)
    args = p.parse_args()

    offline = os.environ.get("LOLPERFMON_OFFLINE", "").lower() in ("1", "true", "yes")
    if offline:
        bundle = build_offline_bundle()
    else:
        ver = latest_version(timeout=30.0)
        if not ver:
            print("Could not fetch patch version")
            sys.exit(1)
        pair = load_ddragon_bundle_with_audit(ver, timeout=args.timeout, full_sr_item_catalog=True)
        bundle = pair[0]
        if bundle is None:
            sys.exit(1)

    cid = "generic_ap" if offline else args.champion
    if cid not in bundle.champions:
        print(f"Champion {cid} not in bundle")
        sys.exit(1)

    starter = args.jungle_starter.strip() or None
    starter = resolve_jungle_starter_item_id(bundle, starter)
    print("patch:", bundle.rules.patch_version)
    print("jungle companions in bundle:", jungle_companion_item_ids_sorted(bundle))
    print("using starter:", starter)

    best_t, score, res = optimal_jungle_sell_timing(
        bundle,
        cid,
        args.t_max,
        jungle_starter_item_id=starter,
        jungle_sell_only_after_level_18=args.sell_only_after_18,
    )
    print("best jungle_sell_at_seconds:", best_t, "(None = never sell)")
    print("total_farm_gold:", round(score, 2))
    print("final_level:", res.final_level, "final_gold:", round(res.final_gold, 2))


if __name__ == "__main__":
    main()
