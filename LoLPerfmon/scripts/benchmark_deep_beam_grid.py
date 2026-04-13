#!/usr/bin/env python3
"""
Grid search: beam_depth in {8,10,12,14,16} × beam_width in {3,4,5,6} for Lux (lane),
Karthus (jungle), Quinn (lane). Compares full-horizon farm gold (beam objective) and
early-game modeled clear power (effective_dps trace from simulate).

max_leaf_evals is set high enough for depth×width² leaf simulations per layer (see
FarmBuildSearch). Requires network Data Dragon unless LOLPERFMON_OFFLINE=1 (then only
generic_ap lane runs).

**Important:** FarmBuildSearch expands prefixes using :func:`state_after_prefix`, which
chains purchases from **starting gold only** (no simulated income). Once the first
purchase is fixed, later beam layers often find **no affordable positive-ΔDPS
marginal** from that snapshot, so ``leaves_evaluated`` stays tiny and **raising
beam_depth into double digits may not explore deeper purchase trees**—all wide/deep
cells can match greedy. Interpret ``leaves_evaluated`` in the output as a diagnostic.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from LoLPerfmon.sim.bundle_factory import build_offline_bundle, load_ddragon_bundle_with_audit
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.ddragon_fetch import latest_version
from LoLPerfmon.sim.greedy_farm_build import beam_refined_farm_build, make_forced_prefix_then_greedy_hook
from LoLPerfmon.sim.jungle_items import jungle_companion_item_ids_sorted
from LoLPerfmon.sim.simulator import PurchasePolicy, simulate

REFERENCE: tuple[tuple[str, FarmMode], ...] = (
    ("lux", FarmMode.LANE),
    ("karthus", FarmMode.JUNGLE),
    ("quinn", FarmMode.LANE),
)

DEPTHS = (8, 10, 12, 14, 16)
WIDTHS = (3, 4, 5, 6)


def _max_leaf_for_grid(max_w: int, max_d: int) -> int:
    """Upper bound on leaf sims: greedy baseline + each beam layer expands ≤ w² prefixes."""
    return 50 + max_d * max_w * max_w


def _auc_dps_early(samples: list[tuple[float, float]], t_end: float) -> float:
    """Piecewise-constant DPS × Δtime from sorted (t, dps) samples, integrated to t_end."""
    if not samples:
        return 0.0
    s = sorted(samples, key=lambda x: x[0])
    total = 0.0
    for i in range(len(s)):
        t0, d0 = s[i]
        if t0 >= t_end:
            break
        t1 = s[i + 1][0] if i + 1 < len(s) else t_end
        t1 = min(t1, t_end)
        if t1 > t0:
            total += d0 * (t1 - t0)
    return total


def _t_reach_fraction(samples: list[tuple[float, float]], frac: float) -> float | None:
    if not samples:
        return None
    peak = max(d for _, d in samples)
    if peak <= 0:
        return None
    thr = peak * frac
    for t, d in sorted(samples, key=lambda x: x[0]):
        if d + 1e-12 >= thr:
            return t
    return None


def analyze_build(
    bundle,
    champion_id: str,
    farm_mode: FarmMode,
    order: tuple[str, ...],
    t_max: float,
    early_horizon: float,
    jungle_starter_item_id: str | None = None,
) -> dict[str, Any]:
    profile = bundle.champions[champion_id]
    items = bundle.items
    hook = make_forced_prefix_then_greedy_hook(profile, items, None, 1e-9, order)
    dps_pairs: list[tuple[float, float]] = []

    def lane_cb(t: float, _k: int, dps: float) -> None:
        dps_pairs.append((t, dps))

    def jungle_cb(t: float, _k: int, dps: float) -> None:
        dps_pairs.append((t, dps))

    res_full = simulate(
        bundle,
        champion_id,
        farm_mode,
        PurchasePolicy(buy_order=()),
        eta_lane=1.0,
        t_max=t_max,
        defer_purchases_until=None,
        purchase_hook=hook,
        on_lane_clear_dps=lane_cb if farm_mode == FarmMode.LANE else None,
        on_jungle_clear_dps=jungle_cb if farm_mode == FarmMode.JUNGLE else None,
        jungle_starter_item_id=jungle_starter_item_id,
    )
    res_early = simulate(
        bundle,
        champion_id,
        farm_mode,
        PurchasePolicy(buy_order=()),
        eta_lane=1.0,
        t_max=early_horizon,
        defer_purchases_until=None,
        purchase_hook=hook,
        jungle_starter_item_id=jungle_starter_item_id,
    )
    peak = max((d for _, d in dps_pairs), default=0.0)
    t80 = _t_reach_fraction(dps_pairs, 0.8)
    auc = _auc_dps_early(dps_pairs, early_horizon)
    return {
        "total_farm_gold": res_full.total_farm_gold,
        "farm_gold_first_horizon": res_early.total_farm_gold,
        "peak_effective_dps": peak,
        "seconds_to_80pct_of_peak_dps": t80,
        "dps_auc_0_early_horizon": auc,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--t-max", type=float, default=3600.0)
    p.add_argument("--early-horizon", type=float, default=900.0, help="Seconds for early farm + DPS integral")
    p.add_argument("--marginal-objective", choices=("dps_per_gold", "horizon_greedy_roi"), default="dps_per_gold")
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--json-out", type=str, default="", help="Write full result rows as JSON lines")
    args = p.parse_args()

    max_w = max(WIDTHS)
    max_d = max(DEPTHS)
    max_leaf = _max_leaf_for_grid(max_w, max_d)

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
            print("Data Dragon bundle unavailable")
            sys.exit(1)

    champs = REFERENCE if not offline else (("generic_ap", FarmMode.LANE),)
    print("patch:", bundle.rules.patch_version, "max_leaf_evals:", max_leaf, "grid depths", DEPTHS, "widths", WIDTHS)
    print(
        "(If leaves_evaluated stays ~4–8, beam stopped early—see module docstring; "
        "depth/width may not affect the chosen build.)"
    )
    rows: list[dict[str, Any]] = []
    json_f = open(args.json_out, "w") if args.json_out else None

    t0 = time.perf_counter()
    for cid, fm in champs:
        if cid not in bundle.champions:
            print(f"skip {cid}: not in bundle")
            continue
        print(f"\n=== {cid.upper()} ({fm.value}) ===")
        best_early: tuple[float, str] | None = None
        for depth in DEPTHS:
            for width in WIDTHS:
                cell_t = time.perf_counter()
                starter_used: str | None = None
                if fm == FarmMode.JUNGLE:
                    best_pack = None
                    best_sid = None
                    for sid in jungle_companion_item_ids_sorted(bundle):
                        pack = beam_refined_farm_build(
                            bundle,
                            cid,
                            t_max=args.t_max,
                            beam_width=width,
                            beam_depth=depth,
                            max_leaf_evals=max_leaf,
                            farm_mode=fm,
                            marginal_objective=args.marginal_objective,
                            jungle_starter_item_id=sid,
                        )
                        if best_pack is None or pack[1] > best_pack[1]:
                            best_pack = pack
                            best_sid = sid
                    assert best_pack is not None and best_sid is not None
                    order, farm_gold, res, meta = best_pack
                    starter_used = best_sid
                else:
                    order, farm_gold, res, meta = beam_refined_farm_build(
                        bundle,
                        cid,
                        t_max=args.t_max,
                        beam_width=width,
                        beam_depth=depth,
                        max_leaf_evals=max_leaf,
                        farm_mode=fm,
                        marginal_objective=args.marginal_objective,
                    )
                names = [bundle.items[i].name if i in bundle.items else i for i in order]
                stats = analyze_build(
                    bundle, cid, fm, order, args.t_max, args.early_horizon, jungle_starter_item_id=starter_used
                )
                row = {
                    "champion": cid,
                    "farm_mode": fm.value,
                    "jungle_starter_item_id": starter_used,
                    "beam_depth": depth,
                    "beam_width": width,
                    "leaves_evaluated": getattr(meta, "leaves_evaluated", None),
                    "beam_meta": str(meta),
                    "total_farm_gold_beam": farm_gold,
                    "buy_order": names,
                    **stats,
                }
                rows.append(row)
                if json_f:
                    json_f.write(json.dumps(row, default=str) + "\n")
                    json_f.flush()
                # Rank early clear: prioritize farm gold in first horizon, then DPS AUC, lower t80
                early_key = (
                    stats["farm_gold_first_horizon"],
                    stats["dps_auc_0_early_horizon"],
                    -(stats["seconds_to_80pct_of_peak_dps"] or 1e9),
                )
                label = f"d={depth} w={width}"
                if best_early is None or early_key > best_early[0]:
                    best_early = (early_key, label)
                if starter_used:
                    jn = bundle.items[starter_used].name if starter_used in bundle.items else starter_used
                    jextra = f" starter={jn}"
                else:
                    jextra = ""
                lv = getattr(meta, "leaves_evaluated", None)
                leaves_s = f"{lv:>4}" if lv is not None else "greedy"
                print(
                    f"  d={depth:2d} w={width}{jextra} leaves={leaves_s} "
                    f"farm3600={farm_gold:10.1f} farm_{int(args.early_horizon)}={stats['farm_gold_first_horizon']:8.1f} "
                    f"auc_dps_{int(args.early_horizon)}={stats['dps_auc_0_early_horizon']:.0f} "
                    f"t_80%peak={stats['seconds_to_80pct_of_peak_dps']} peak_dps={stats['peak_effective_dps']:.1f} "
                    f"({time.perf_counter() - cell_t:.1f}s)"
                )
        if best_early:
            print(f"  >> best early-game proxy (farm@{int(args.early_horizon)}s, auc dps, then faster t@80%): {best_early[1]}")

    print(f"\nTotal elapsed: {time.perf_counter() - t0:.1f}s")
    if json_f:
        json_f.close()


if __name__ == "__main__":
    main()
