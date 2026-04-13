#!/usr/bin/env python3
"""
CLI: greedy / beam farm builds for default champions (Data Dragon when online).

See OPTIMIZATION_CRITERIA.md. Set LOLPERFMON_OFFLINE=1 for offline bundle only.
"""

from __future__ import annotations

import argparse
import os
import sys

# Repo root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from LoLPerfmon.sim.bundle_factory import build_offline_bundle, load_ddragon_bundle_with_audit
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.ddragon_fetch import latest_version
from LoLPerfmon.sim.greedy_farm_build import beam_refined_farm_build
from LoLPerfmon.sim.marginal_clear import clear_upgrade_report


def main() -> None:
    p = argparse.ArgumentParser(description="Greedy/beam lane or jungle farm build (Lux, Karthus, Quinn)")
    p.add_argument("--t-max", type=float, default=3600.0)
    p.add_argument("--beam-width", type=int, default=3)
    p.add_argument("--beam-depth", type=int, default=1)
    p.add_argument("--max-leaf-evals", type=int, default=27)
    p.add_argument(
        "--farm-mode",
        choices=("lane", "jungle"),
        default="lane",
        help="Lane = minion waves only; jungle = camp cycles only (Classic SR 5v5 model).",
    )
    p.add_argument(
        "--marginal-objective",
        choices=("dps_per_gold", "horizon_greedy_roi"),
        default="dps_per_gold",
        help="How to rank next-item candidates at empty prefix (horizon uses nested sims; costly).",
    )
    p.add_argument("--horizon-candidate-cap", type=int, default=48)
    p.add_argument("--timeout", type=float, default=45.0)
    args = p.parse_args()

    farm_mode = FarmMode.LANE if args.farm_mode == "lane" else FarmMode.JUNGLE

    offline = os.environ.get("LOLPERFMON_OFFLINE", "").lower() in ("1", "true", "yes")
    if offline:
        bundle = build_offline_bundle()
    else:
        ver = latest_version(timeout=30.0)
        if not ver:
            print("Could not fetch patch version; set LOLPERFMON_OFFLINE=1 or fix network")
            sys.exit(1)
        pair = load_ddragon_bundle_with_audit(ver, timeout=args.timeout, full_sr_item_catalog=True)
        bundle = pair[0]
        if bundle is None:
            print("Data Dragon bundle unavailable")
            sys.exit(1)

    print("patch:", bundle.rules.patch_version)
    print("farm_mode:", farm_mode.value, "beam_depth:", args.beam_depth, "marginal_objective:", args.marginal_objective)
    champs = ("lux", "karthus", "quinn") if not offline else ("generic_ap",)
    for cid in champs:
        if cid not in bundle.champions:
            print(f"skip {cid}: not in bundle")
            continue
        order, farm_gold, res, meta = beam_refined_farm_build(
            bundle,
            cid,
            t_max=args.t_max,
            beam_width=args.beam_width,
            beam_depth=args.beam_depth,
            max_leaf_evals=args.max_leaf_evals,
            farm_mode=farm_mode,
            marginal_objective=args.marginal_objective,
            horizon_candidate_cap=args.horizon_candidate_cap,
        )
        names = [bundle.items[i].name if i in bundle.items else i for i in order]
        print("---", cid.upper(), "---")
        print("total_farm_gold:", round(farm_gold, 2))
        print("meta:", meta)
        print("buy_order:", " -> ".join(names) if names else "(none)")
        sat, rows = clear_upgrade_report(bundle, cid, res)
        print("clear_upgrade saturated:", sat, "affordable_dps_upgrades:", len(rows))


if __name__ == "__main__":
    main()
