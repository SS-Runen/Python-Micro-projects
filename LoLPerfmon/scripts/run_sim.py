#!/usr/bin/env python3
"""Standard entry point: beam-search farm build for one or more champions.

Simulation uses game time 00:00: starting gold, optional starter item, then forward
simulation for ``--t-max`` seconds.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from LoLPerfmon.data.loaders import data_root_default, load_bundle
from LoLPerfmon.sim.config import DEFAULT_JUNGLE_UNIT_ID, DEFAULT_LANE_UNIT_ID
from LoLPerfmon.sim.runner import (
    default_jungle_monster,
    default_lane_minion,
    farm_mode_from_role,
    resolve_starter_item_id,
)
from LoLPerfmon.sim.search import BeamSearchConfig, beam_search_farm_build
from LoLPerfmon.sim.sim_logging import configure_sim_logging_stderr
from LoLPerfmon.sim.simulator import simulate_with_buy_order


def main() -> None:
    p = argparse.ArgumentParser(
        description="Optimize farm build (beam search) from 00:00 game time.",
    )
    mx = p.add_mutually_exclusive_group(required=True)
    mx.add_argument("--champion", type=str, metavar="ID", help="One champion id (e.g. lux)")
    mx.add_argument("--champions", nargs="+", metavar="ID", help="Batch: several champion ids")
    p.add_argument(
        "--role",
        type=str,
        choices=("laner", "jungler"),
        required=True,
        help="Lane (laner) or jungle (jungler) farm model",
    )
    p.add_argument(
        "--starter-item",
        type=str,
        default=None,
        metavar="NAME_OR_ID",
        help="Starting item (id or display name). Default: amplifying_tome (laner) or dagger (jungler) when present",
    )
    p.add_argument(
        "--no-starter",
        action="store_true",
        help="No starting item purchase (full 500g wallet, empty inventory)",
    )
    p.add_argument(
        "--t-max",
        type=float,
        default=600.0,
        help="Simulate this many seconds of game time from 00:00 (default: 600)",
    )
    p.add_argument("--beam-width", type=int, default=4)
    p.add_argument("--max-depth", type=int, default=4)
    p.add_argument("--max-leaf-evals", type=int, default=128)
    p.add_argument(
        "--leaf-score",
        choices=("total_farm_gold", "total_clear_units"),
        default="total_farm_gold",
    )
    p.add_argument(
        "--ensure-champion",
        action="store_true",
        help="If champion JSON is missing, run Wiki + Data Dragon ingest then retry",
    )
    p.add_argument(
        "--log-interval",
        type=float,
        default=0.0,
        metavar="SEC",
        help=(
            "After search, replay the best buy order once and log game state every SEC seconds "
            "(e.g. 10 for troubleshooting). Single-champion runs only; 0=off (default)."
        ),
    )
    args = p.parse_args()

    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    mode = farm_mode_from_role(args.role)
    try:
        starter_id = resolve_starter_item_id(
            mode,
            args.starter_item,
            no_starter=args.no_starter,
            items_catalog=items,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    lane_u = default_lane_minion(units)
    jung_u = default_jungle_monster(units)
    if mode.value == "lane" and lane_u is None:
        print(f"Missing default lane unit {DEFAULT_LANE_UNIT_ID!r} (data/minions)", file=sys.stderr)
        sys.exit(1)
    if mode.value == "jungle" and jung_u is None:
        print(f"Missing default jungle unit {DEFAULT_JUNGLE_UNIT_ID!r} (data/monsters)", file=sys.stderr)
        sys.exit(1)

    cfg = BeamSearchConfig(
        beam_width=args.beam_width,
        max_depth=args.max_depth,
        max_leaf_evals=args.max_leaf_evals,
        t_max=args.t_max,
    )
    cands = tuple(sorted(items.keys()))

    ids: list[str]
    if args.champion:
        ids = [args.champion.lower()]
    else:
        ids = [c.lower() for c in args.champions]

    for cid in ids:
        if cid not in ch and args.ensure_champion:
            from LoLPerfmon.ingest.champion_sync import sync_champion_to_disk

            try:
                sync_champion_to_disk(root, cid)
            except (OSError, KeyError, RuntimeError, ValueError) as ex:
                print(f"ensure-champion failed: {ex}", file=sys.stderr)
                sys.exit(1)
            ch, items, units, _ = load_bundle(root)
            lane_u = default_lane_minion(units)
            jung_u = default_jungle_monster(units)

        if cid not in ch:
            print(f"Unknown champion {cid}", file=sys.stderr)
            if len(ids) == 1:
                sys.exit(1)
            continue

        order, score, res = beam_search_farm_build(
            ch[cid],
            mode,
            items,
            cands,
            lane_minion=lane_u,
            jungle_monster=jung_u,
            cfg=cfg,
            leaf_score=args.leaf_score,
            starter_item_id=starter_id,
        )
        starter_note = starter_id or "(none)"
        if len(ids) == 1:
            print(f"champion={cid} role={args.role} starter={starter_note} t_max={args.t_max}")
            print("buy_order:", " -> ".join(order) if order else "(none)")
            print("score:", score)
            print("total_farm_gold:", res.total_farm_gold)
            print("lane_minions:", res.total_lane_minions_cleared, "jungle:", res.total_jungle_monsters_cleared)
            if args.log_interval and args.log_interval > 0:
                configure_sim_logging_stderr()
                print("--- diagnostic replay (best buy order, INFO on stderr) ---", file=sys.stderr)
                simulate_with_buy_order(
                    ch[cid],
                    mode,
                    items,
                    order,
                    args.t_max,
                    lane_minion=lane_u,
                    jungle_monster=jung_u,
                    starter_item_id=starter_id,
                    log_interval_sec=args.log_interval,
                )
        else:
            print(f"{cid}: score={score:.2f} starter={starter_note} order={' -> '.join(order)}")


if __name__ == "__main__":
    main()
