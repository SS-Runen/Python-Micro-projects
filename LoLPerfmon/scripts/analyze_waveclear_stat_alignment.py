#!/usr/bin/env python3
"""
Rank items by modeled waveclear stat alignment and optional per-build DPS steps.

For each champion, infers **AP** vs **AD** vs **mixed** primary ability scaling from Data Dragon spell
coefficients (or :class:`KitParams` fallback), lists the top ``--top-n`` items in the wave-clear catalog
by :func:`~LoLPerfmon.sim.item_heuristics.modeled_dps_uplift_per_gold` among stat-compatible items, and
optionally prints :func:`~LoLPerfmon.sim.kit_stat_alignment.marginal_dps_along_build_order` for a
comma-separated purchase order.

Repository root on ``PYTHONPATH``; live Data Dragon unless ``LOLPERFMON_OFFLINE=1``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from LoLPerfmon.sim.bundle_factory import build_offline_bundle, load_ddragon_bundle_with_audit
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.ddragon_fetch import latest_version
from LoLPerfmon.sim.kit_stat_alignment import (
    filter_waveclear_catalog_stat_aligned,
    infer_primary_ability_damage_axis,
    item_matches_primary_damage_axis,
    marginal_dps_along_build_order,
    rank_stat_aligned_items_by_modeled_dps_per_gold,
)


def _parse_csv(s: str) -> frozenset[str]:
    return frozenset(x.strip().lower() for x in (s or "").split(",") if x.strip())


def main() -> None:
    p = argparse.ArgumentParser(description="Stat-aligned waveclear item ranking and DPS steps.")
    p.add_argument("--champions", required=True, help="Comma-separated champion ids (e.g. lux,quinn,karthus).")
    p.add_argument("--farm-mode", choices=("lane", "jungle"), default="lane")
    p.add_argument("--level", type=int, default=11, help="Level for DPS and spell rank (default 11).")
    p.add_argument("--top-n", type=int, default=40, help="How many stat-aligned items to list per champion.")
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument(
        "--build-order",
        default="",
        help="Optional comma-separated item ids for marginal_dps_along_build_order (e.g. 1056,1056,...).",
    )
    p.add_argument("--out", type=Path, default=None, help="Optional output file (default: stdout only).")
    args = p.parse_args()

    offline = os.environ.get("LOLPERFMON_OFFLINE", "").lower() in ("1", "true", "yes")
    if offline:
        bundle = build_offline_bundle()
    else:
        ver = latest_version(timeout=30.0)
        if not ver:
            print("Could not fetch patch version; set LOLPERFMON_OFFLINE=1", file=sys.stderr)
            sys.exit(1)
        pair = load_ddragon_bundle_with_audit(ver, timeout=args.timeout, full_sr_item_catalog=True)
        bundle = pair[0]
        if bundle is None:
            print("Data Dragon bundle unavailable", file=sys.stderr)
            sys.exit(1)

    farm_mode = FarmMode.LANE if args.farm_mode == "lane" else FarmMode.JUNGLE
    cids = sorted(_parse_csv(args.champions))
    lines: list[str] = [
        f"patch={bundle.rules.patch_version}",
        f"farm_mode={farm_mode.value} level={args.level} top_n={args.top_n}",
        "",
    ]

    for cid in cids:
        if cid not in bundle.champions:
            lines.append(f"# skip {cid}: not in bundle")
            lines.append("")
            continue
        profile = bundle.champions[cid]
        axis, ap_c, ad_c = infer_primary_ability_damage_axis(profile, level=args.level)
        cat = filter_waveclear_catalog_stat_aligned(
            bundle.items, farm_mode, profile, level=args.level
        )
        lines.append(f"=== {cid.upper()} ===")
        lines.append(
            f"inferred_primary_ability_axis={axis} dominant_line_ap_coeff={ap_c:.6g} dominant_line_ad_coeff={ad_c:.6g}"
        )
        lines.append(f"stat_aligned_catalog_size={len(cat)}")
        ranked = rank_stat_aligned_items_by_modeled_dps_per_gold(
            profile, cat, level=args.level
        )
        lines.append(f"stat_aligned_top_{args.top_n}_by_modeled_dps_per_gold (empty inventory proxy):")
        for i, (iid, uplift, ax_r) in enumerate(ranked[: args.top_n], 1):
            nm = cat[iid].name if iid in cat else iid
            lines.append(f"  {i:3d}. {nm}  [{iid}]  uplift/gold={uplift:.6f}  axis={ax_r}")
        compat_count = sum(1 for iid, it in cat.items() if item_matches_primary_damage_axis(it, axis))
        lines.append(f"items_matching_axis_count={compat_count} (of {len(cat)} in closed catalog)")
        if args.build_order:
            order = tuple(x.strip() for x in args.build_order.split(",") if x.strip())
            steps = marginal_dps_along_build_order(profile, order, cat, level=args.level)
            lines.append("marginal_dps_along_build_order:")
            for row in steps:
                lines.append(
                    f"  step {row['step']}: {row['item_id']}  Δdps={row['delta_dps']:.4f} "
                    f"Δdps/cost={row['delta_dps_per_item_total_cost']:.6f}  dps_after={row['dps_after']:.4f}"
                )
        lines.append("")

    text = "\n".join(lines)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
