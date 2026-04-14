#!/usr/bin/env python3
"""
Batch beam search for wave-clear–oriented builds (leaf_score=total_clear_units).

Lane: lux, quinn, kayle (AP pool via --kayle-stat-align).
Jungle: karthus, briar (best jungle pet per champion).

Requires network + LOLPERFMON_OFFLINE=0 for full Data Dragon champions.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from LoLPerfmon.sim.bundle_factory import load_ddragon_bundle_with_audit

# Data Dragon champion JSON keys (display names) — must include every champion this script runs.
_WAVECLEAR_BATCH_CHAMPION_KEYS: tuple[str, ...] = ("Lux", "Karthus", "Quinn", "Kayle", "Briar")
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.ddragon_fetch import latest_version
from LoLPerfmon.sim.greedy_farm_build import beam_refined_farm_build
from LoLPerfmon.sim.item_heuristics import (
    DEFAULT_WAVECLEAR_EXCLUDE_TAGS,
    waveclear_relevant_item_catalog,
)
from LoLPerfmon.sim.jungle_items import is_jungle_companion_item, jungle_pet_companion_item_ids_sorted
from LoLPerfmon.sim.models import ItemDef


def _catalog(
    bundle,
    farm_mode: FarmMode,
    champion_id: str,
    *,
    reference_level: int,
    allow_full_catalog_fallback: bool,
) -> dict[str, ItemDef]:
    merged_ex = DEFAULT_WAVECLEAR_EXCLUDE_TAGS
    cat = waveclear_relevant_item_catalog(
        bundle.items,
        farm_mode,
        bundle.champions[champion_id],
        exclude_tags=merged_ex,
        reference_level=reference_level,
        allow_full_catalog_fallback=allow_full_catalog_fallback,
    )
    if farm_mode == FarmMode.JUNGLE:
        merged = dict(cat)
        for iid, it in bundle.items.items():
            if is_jungle_companion_item(it):
                merged[iid] = it
        cat = merged
    return cat


def main() -> None:
    p = argparse.ArgumentParser(description="Wave-clear optimal batch (total_clear_units leaf).")
    p.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".local" / "waveclear_optimal_batch.txt",
    )
    p.add_argument("--t-max", type=float, default=3600.0)
    p.add_argument("--beam-depth", type=int, default=8)
    p.add_argument("--beam-width", type=int, default=64)
    p.add_argument("--beam-branching-width", type=int, default=64)
    p.add_argument("--beam-survivors", type=int, default=64)
    p.add_argument("--max-leaf-evals", type=int, default=4096)
    p.add_argument("--horizon-candidate-cap", type=int, default=128)
    p.add_argument("--timeout", type=float, default=90.0)
    p.add_argument("--path-into-weight", type=float, default=0.65)
    p.add_argument("--ideal-target-top-k", type=int, default=16)
    p.add_argument("--ideal-path-boost", type=float, default=0.25)
    p.add_argument("--marginal-reference-level", type=int, default=11)
    p.add_argument("--marginal-income-cap", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--use-level-weighted-marginal", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--normalize-marginal-path-blend", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--allow-full-catalog-fallback", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument(
        "--kayle-stat-align-level",
        type=int,
        default=11,
        help="Deprecated compatibility flag; use --marginal-reference-level.",
    )
    args = p.parse_args()

    offline = os.environ.get("LOLPERFMON_OFFLINE", "").lower() in ("1", "true", "yes")
    if offline:
        print("Set LOLPERFMON_OFFLINE=0 for live Data Dragon (Kayle, Briar, etc.).", file=sys.stderr)
        sys.exit(1)

    ver = latest_version(timeout=30.0)
    if not ver:
        print("Could not fetch patch version", file=sys.stderr)
        sys.exit(1)
    pair = load_ddragon_bundle_with_audit(
        ver,
        timeout=args.timeout,
        full_sr_item_catalog=True,
        champion_keys=_WAVECLEAR_BATCH_CHAMPION_KEYS,
    )
    bundle = pair[0]
    if bundle is None:
        print("Data Dragon bundle unavailable", file=sys.stderr)
        sys.exit(1)

    runs: list[tuple[str, FarmMode, bool]] = [
        ("lux", FarmMode.LANE, False),
        ("quinn", FarmMode.LANE, False),
        ("kayle", FarmMode.LANE, True),
        ("karthus", FarmMode.JUNGLE, False),
        ("briar", FarmMode.JUNGLE, False),
    ]

    lines: list[str] = [
        "LoLPerfmon — beam search wave-clear builds (leaf_score=total_clear_units, marginal_objective=horizon_greedy_roi)",
        f"patch={bundle.rules.patch_version}",
        (
            f"beam_depth={args.beam_depth} beam_width={args.beam_width} "
            f"branch={args.beam_branching_width} survivors={args.beam_survivors} "
            f"max_leaf_evals={args.max_leaf_evals} t_max={args.t_max}"
        ),
        (
            f"path_into_weight={args.path_into_weight} ideal_top_k={args.ideal_target_top_k} "
            f"ideal_path_boost={args.ideal_path_boost} marginal_ref_level={args.marginal_reference_level}"
        ),
        (
            f"marginal_income_cap={args.marginal_income_cap} "
            f"use_level_weighted_marginal={args.use_level_weighted_marginal} "
            f"normalize_marginal_path_blend={args.normalize_marginal_path_blend}"
        ),
        "lane: lux, quinn, kayle via waveclear-relevant catalog (DPS + stat-axis + recipes)",
        "jungle: karthus, briar (best pet chosen)",
        "",
    ]

    for cid, farm_mode, _kayle_align in runs:
        if cid not in bundle.champions:
            lines.append(f"=== {cid.upper()} SKIP (not in bundle) ===")
            lines.append("")
            continue
        filtered = _catalog(
            bundle,
            farm_mode,
            cid,
            reference_level=args.marginal_reference_level,
            allow_full_catalog_fallback=args.allow_full_catalog_fallback,
        )
        if not filtered:
            lines.append(f"=== {cid.upper()} SKIP (empty catalog) ===")
            lines.append("")
            continue
        champ_bundle = replace(bundle, items=filtered)
        marginal_cap = bool(args.marginal_income_cap)
        if farm_mode == FarmMode.JUNGLE:
            best = None
            best_sid = None
            for sid in jungle_pet_companion_item_ids_sorted(champ_bundle):
                pack = beam_refined_farm_build(
                    champ_bundle,
                    cid,
                    t_max=args.t_max,
                    beam_width=args.beam_width,
                    beam_branching_width=args.beam_branching_width,
                    beam_survivors=args.beam_survivors,
                    beam_depth=args.beam_depth,
                    max_leaf_evals=args.max_leaf_evals,
                    farm_mode=farm_mode,
                    marginal_objective="horizon_greedy_roi",
                    horizon_candidate_cap=args.horizon_candidate_cap,
                    jungle_starter_item_id=sid,
                    marginal_income_cap=marginal_cap,
                    leaf_score="total_clear_units",
                    extrapolate_lane_waves=True,
                    path_into_weight=args.path_into_weight,
                    ideal_target_top_k=args.ideal_target_top_k,
                    ideal_path_boost=args.ideal_path_boost,
                    marginal_reference_level=args.marginal_reference_level,
                    use_level_weighted_marginal=args.use_level_weighted_marginal,
                    normalize_marginal_path_blend=args.normalize_marginal_path_blend,
                    allow_full_catalog_fallback=args.allow_full_catalog_fallback,
                )
                if best is None or pack[1] > best[1]:
                    best = pack
                    best_sid = sid
            assert best is not None and best_sid is not None
            order, primary_score, res, meta = best
            starter = champ_bundle.items[best_sid].name if best_sid in champ_bundle.items else best_sid
        else:
            order, primary_score, res, meta = beam_refined_farm_build(
                champ_bundle,
                cid,
                t_max=args.t_max,
                beam_width=args.beam_width,
                beam_branching_width=args.beam_branching_width,
                beam_survivors=args.beam_survivors,
                beam_depth=args.beam_depth,
                max_leaf_evals=args.max_leaf_evals,
                farm_mode=farm_mode,
                marginal_objective="horizon_greedy_roi",
                horizon_candidate_cap=args.horizon_candidate_cap,
                marginal_income_cap=marginal_cap,
                leaf_score="total_clear_units",
                extrapolate_lane_waves=True,
                path_into_weight=args.path_into_weight,
                ideal_target_top_k=args.ideal_target_top_k,
                ideal_path_boost=args.ideal_path_boost,
                marginal_reference_level=args.marginal_reference_level,
                use_level_weighted_marginal=args.use_level_weighted_marginal,
                normalize_marginal_path_blend=args.normalize_marginal_path_blend,
                allow_full_catalog_fallback=args.allow_full_catalog_fallback,
            )
            starter = None

        names = [champ_bundle.items[i].name if i in champ_bundle.items else i for i in order]
        lines.append(f"=== {cid.upper()} ({farm_mode.value}) ===")
        if starter:
            lines.append(f"jungle_starter: {starter}")
        if cid == "kayle":
            lines.append(f"reference_level: {args.marginal_reference_level}")
        lines.append(f"total_clear_units (leaf): {primary_score:.4f}")
        lines.append(
            f"clears: lane_minions={res.total_lane_minions_cleared:.2f} jungle_monsters={res.total_jungle_monsters_cleared:.2f}"
        )
        lines.append(f"total_farm_gold: {res.total_farm_gold:.2f}")
        lines.append(f"meta: {meta}")
        lines.append("buy_order: " + (" -> ".join(names) if names else "(none)"))
        lines.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
