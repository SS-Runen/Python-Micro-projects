#!/usr/bin/env python3
"""CLI: beam search farm build for one champion."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from LoLPerfmon.data.loaders import data_root_default, load_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.search import BeamSearchConfig, beam_search_farm_build


def main() -> None:
    p = argparse.ArgumentParser(description="Optimize farm build (beam search).")
    p.add_argument("--champion", type=str, required=True)
    p.add_argument("--mode", choices=("lane", "jungle"), required=True)
    p.add_argument("--t-max", type=float, default=600.0)
    p.add_argument("--beam-width", type=int, default=4)
    p.add_argument("--max-depth", type=int, default=4)
    p.add_argument("--max-leaf-evals", type=int, default=128)
    p.add_argument("--leaf-score", choices=("total_farm_gold", "total_clear_units"), default="total_farm_gold")
    p.add_argument(
        "--ensure-champion",
        action="store_true",
        help="If champion data is missing under data/champions, run Wiki + Data Dragon ingest then retry load",
    )
    args = p.parse_args()
    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    cid = args.champion.lower()
    if cid not in ch and args.ensure_champion:
        from LoLPerfmon.ingest.champion_sync import sync_champion_to_disk

        try:
            sync_champion_to_disk(root, cid)
        except (OSError, KeyError, RuntimeError, ValueError) as ex:
            print(f"ensure-champion failed: {ex}", file=sys.stderr)
            sys.exit(1)
        ch, items, units, _ = load_bundle(root)
    if cid not in ch:
        print(f"Unknown champion {cid}", file=sys.stderr)
        sys.exit(1)
    mode = FarmMode.LANE if args.mode == "lane" else FarmMode.JUNGLE
    lane_u = units.get("lane_melee")
    jung_u = units.get("raptor_small")
    cfg = BeamSearchConfig(
        beam_width=args.beam_width,
        max_depth=args.max_depth,
        max_leaf_evals=args.max_leaf_evals,
        t_max=args.t_max,
    )
    cands = tuple(sorted(items.keys()))
    order, score, res = beam_search_farm_build(
        ch[cid],
        mode,
        items,
        cands,
        lane_minion=lane_u,
        jungle_monster=jung_u,
        cfg=cfg,
        leaf_score=args.leaf_score,
    )
    print("buy_order:", " -> ".join(order) if order else "(none)")
    print("score:", score)
    print("total_farm_gold:", res.total_farm_gold)
    print("lane_minions:", res.total_lane_minions_cleared, "jungle:", res.total_jungle_monsters_cleared)


if __name__ == "__main__":
    main()
