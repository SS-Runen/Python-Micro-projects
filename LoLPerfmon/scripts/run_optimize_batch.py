#!/usr/bin/env python3
"""Batch farm build optimization for multiple champions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from LoLPerfmon.data.loaders import data_root_default, load_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.search import BeamSearchConfig, beam_search_farm_build


def main() -> None:
    p = argparse.ArgumentParser(description="Batch optimize farm builds.")
    p.add_argument("--champions", nargs="+", required=True)
    p.add_argument("--mode", choices=("lane", "jungle"), required=True)
    p.add_argument("--t-max", type=float, default=600.0)
    args = p.parse_args()
    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    mode = FarmMode.LANE if args.mode == "lane" else FarmMode.JUNGLE
    lane_u = units.get("lane_melee")
    jung_u = units.get("raptor_small")
    cfg = BeamSearchConfig(t_max=args.t_max, beam_width=4, max_depth=3, max_leaf_evals=64)
    cands = tuple(sorted(items.keys()))
    for cid in args.champions:
        k = cid.lower()
        if k not in ch:
            print(f"skip unknown {cid}")
            continue
        order, score, res = beam_search_farm_build(
            ch[k],
            mode,
            items,
            cands,
            lane_minion=lane_u,
            jungle_monster=jung_u,
            cfg=cfg,
        )
        print(f"{k}: score={score:.2f} order={' -> '.join(order)}")


if __name__ == "__main__":
    main()
