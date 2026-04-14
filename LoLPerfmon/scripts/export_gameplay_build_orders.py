#!/usr/bin/env python3
"""
Export beam-searched farm builds to a local file for gameplay reference.

Writes under ``LoLPerfmon/.local/`` (gitignored). Default file
``waveclear_early_dps_lux_quinn_karthus.txt`` uses ``leaf_score=early_dps_auc`` so the beam
maximizes modeled **∫ effective DPS dt** over ``--early-horizon-seconds``.

Use ``--leaf-score total_farm_gold`` to optimize full-horizon farm income instead.
Use ``--leaf-score total_clear_units`` to maximize modeled **minion** (lane) or **monster** (jungle) clears (see ``OPTIMIZATION_CRITERIA.md``); this combination **defaults** ``marginal_objective=horizon_greedy_roi`` so the first purchase is ranked by nested full-sim Δclears, not only myopic tick derivatives. Override with ``--marginal-objective dps_per_gold`` if needed. Jungle runs with ``marginal_income_cap=True`` so clear-tick marginals apply.

By default, **wave-clear catalog heuristics** apply (see ``sim/item_heuristics.py``): layered tag excludes
(Support, GoldPer, consumables, trinkets, vision), optional ``--require-item-tags``, lane-specific removal of
jungle pet starters, **downward recipe closure** so components stay available for parents, and (jungle) merge of
**companion** item defs from the full bundle. Disable with ``--no-waveclear-heuristics`` and use only
``--exclude-item-tags`` / ``--require-item-tags`` if needed.

Optional **stat-aligned waveclear pool** (``--stat-align-waveclear``): after tag/lane/jungle rules, restrict
candidate items to those whose stats match the champion’s inferred primary **ability** scaling (AP vs AD
from Data Dragon spell coefficients, or :class:`KitParams` fallback), plus recipe closure. See
``sim/kit_stat_alignment.py`` and ``scripts/analyze_waveclear_stat_alignment.py`` for ranked lists and
per-step modeled DPS along a purchase order.

Optional **item tag filters** (comma-separated Data Dragon tags): ``--exclude-item-tags Support`` adds to the
default exclude set when heuristics are on; ``--require-item-tags Damage`` keeps only items tagged Damage
(combine carefully so the catalog stays non-empty). Use ``--only-champions lux`` (etc.) to run a **single**
REFERENCE champion with a role-specific ``--require-item-tags``.

**Six terminal items (default on):** ``--six-terminal-items`` runs each sim with
``t_max=inf``, lane wave extrapolation, and an early stop when **six inventory slots** hold
**build endpoints** (Data Dragon ``into`` empty — finished legendaries, boots, etc.; no
unfinished components). Jungle includes the starter pet: it must be terminal in the item
graph for the stop to fire. A **simulated-time cap** (``--six-terminal-max-seconds``, default
4h) ends the run if six endpoints are not reached yet (see output flags). Use
``--no-six-terminal-items`` for a fixed ``--t-max`` horizon without that constraint.

Patch from Data Dragon unless ``LOLPERFMON_OFFLINE=1``. Item catalog uses **ranked Summoner's
Rift** filtering (``load_ddragon_bundle_with_audit(..., ranked_summoners_rift_only=True)``).
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from LoLPerfmon.sim.bundle_factory import build_offline_bundle, load_ddragon_bundle_with_audit
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.ddragon_fetch import latest_version
from LoLPerfmon.sim.greedy_farm_build import beam_refined_farm_build, make_early_stop_six_build_endpoints
from LoLPerfmon.sim.item_heuristics import DEFAULT_WAVECLEAR_EXCLUDE_TAGS, filter_waveclear_item_catalog
from LoLPerfmon.sim.kit_stat_alignment import (
    infer_primary_ability_damage_axis,
    marginal_dps_along_build_order,
)
from LoLPerfmon.sim.item_tag_filters import filter_items_by_tags
from LoLPerfmon.sim.jungle_items import is_jungle_companion_item, jungle_pet_companion_item_ids_sorted
from LoLPerfmon.sim.models import ItemDef, is_build_endpoint_item
from LoLPerfmon.sim.simulator import (
    SimulationState,
    default_clear_count_score,
    gold_flow_reconciliation_error,
    gold_income_breakdown,
)

# Defaults match the grid winner in ``benchmark_deep_beam_grid.py`` (depth=8, width=3, same
# max_leaf_evals budget as the widest/deepest grid cell: 50 + 16×6²).
DEFAULT_T_MAX = 3600.0
DEFAULT_BEAM_DEPTH = 8
DEFAULT_BEAM_WIDTH = 3
DEFAULT_MAX_LEAF_EVALS = 626
DEFAULT_HORIZON_CAP = 48
DEFAULT_OUT = Path(__file__).resolve().parents[1] / ".local" / "waveclear_early_dps_lux_quinn_karthus.txt"
DEFAULT_LEAF_SCORE = "early_dps_auc"
DEFAULT_EARLY_HORIZON = 900.0


def _parse_item_tag_csv(s: str) -> frozenset[str]:
    return frozenset(t.strip() for t in (s or "").split(",") if t.strip())


def _parse_only_champions_csv(s: str) -> frozenset[str] | None:
    xs = frozenset(x.strip().lower() for x in (s or "").split(",") if x.strip())
    return xs if xs else None


def _six_endpoints_or_max_clock(
    items: dict[str, ItemDef],
    max_game_seconds: float,
):
    """Stop at six build endpoints, or when simulated clock reaches max_game_seconds (safety bound)."""

    inner = make_early_stop_six_build_endpoints(items)

    def early_stop(state: SimulationState) -> bool:
        if inner(state):
            return True
        return state.time_seconds >= max_game_seconds

    return early_stop


REFERENCE: tuple[tuple[str, FarmMode, bool], ...] = (
    ("lux", FarmMode.LANE, True),
    ("quinn", FarmMode.LANE, True),
    ("karthus", FarmMode.JUNGLE, False),
)


def main() -> None:
    p = argparse.ArgumentParser(description="Write beam farm buy orders to a local gameplay file.")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output path (default: LoLPerfmon/.local/...)")
    p.add_argument("--t-max", type=float, default=DEFAULT_T_MAX)
    p.add_argument("--beam-depth", type=int, default=DEFAULT_BEAM_DEPTH)
    p.add_argument("--beam-width", type=int, default=DEFAULT_BEAM_WIDTH)
    p.add_argument("--max-leaf-evals", type=int, default=DEFAULT_MAX_LEAF_EVALS)
    p.add_argument(
        "--marginal-objective",
        choices=("dps_per_gold", "horizon_greedy_roi"),
        default=None,
        help="Empty-prefix candidate ranking. Default: horizon_greedy_roi when --leaf-score "
        "total_clear_units; otherwise dps_per_gold.",
    )
    p.add_argument(
        "--leaf-score",
        choices=("early_dps_auc", "total_farm_gold", "farm_gold_per_gold_spent", "total_clear_units"),
        default=DEFAULT_LEAF_SCORE,
        help="Beam leaf metric: total_clear_units = max lane minions / jungle monsters cleared (simulator model).",
    )
    p.add_argument(
        "--early-horizon-seconds",
        type=float,
        default=DEFAULT_EARLY_HORIZON,
        help="Upper bound for early_dps_auc integral (simulated clock).",
    )
    p.add_argument("--horizon-candidate-cap", type=int, default=DEFAULT_HORIZON_CAP)
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument(
        "--six-terminal-items",
        dest="six_terminal_items",
        action="store_true",
        default=True,
        help="Run until 6 build-endpoint items fill the bag (t_max=inf, wave extrapolation). Default: on.",
    )
    p.add_argument(
        "--no-six-terminal-items",
        dest="six_terminal_items",
        action="store_false",
        help="Use fixed --t-max only (no six-endpoint stop).",
    )
    p.add_argument(
        "--six-terminal-max-seconds",
        type=float,
        default=4 * 3600.0,
        help="Max simulated game time per inner simulation when using six-terminal mode "
        "(stops early if reached before 6 endpoints; increase if builds rarely complete).",
    )
    p.add_argument(
        "--exclude-item-tags",
        default="",
        metavar="TAGS",
        help="Comma-separated Data Dragon tags: exclude any item whose tags intersect this set (e.g. Support).",
    )
    p.add_argument(
        "--require-item-tags",
        default="",
        metavar="TAGS",
        help="Comma-separated tags: keep only items that have at least one listed tag (empty = no filter).",
    )
    p.add_argument(
        "--no-waveclear-heuristics",
        action="store_true",
        help="Do not apply layered wave-clear catalog filter (see sim/item_heuristics.py); tag args only.",
    )
    p.add_argument(
        "--only-champions",
        default="",
        metavar="IDS",
        help="Comma-separated champion ids to include (e.g. lux,quinn,karthus). Default: all in REFERENCE.",
    )
    p.add_argument(
        "--stat-align-waveclear",
        action="store_true",
        help="Restrict shop to items aligned with inferred primary AP/AD ability scaling (see kit_stat_alignment).",
    )
    p.add_argument(
        "--stat-align-level",
        type=int,
        default=11,
        help="Champion level for spell-coeff rank and axis inference when --stat-align-waveclear (default 11).",
    )
    p.add_argument(
        "--print-modeled-dps-steps",
        action="store_true",
        help="Append per-purchase Δeffective_dps table (fixed level; not farm sim). Implied by --stat-align-waveclear.",
    )
    args = p.parse_args()

    marginal_objective: str
    if args.marginal_objective is not None:
        marginal_objective = args.marginal_objective
    elif args.leaf_score == "total_clear_units":
        marginal_objective = "horizon_greedy_roi"
    elif args.leaf_score == "total_farm_gold":
        marginal_objective = "horizon_greedy_roi"
    else:
        marginal_objective = "dps_per_gold"

    offline = os.environ.get("LOLPERFMON_OFFLINE", "").lower() in ("1", "true", "yes")
    six_mode = args.six_terminal_items
    if offline and six_mode:
        print(
            "LOLPERFMON_OFFLINE: disabling six-terminal-items (use Data Dragon for full builds).",
            file=sys.stderr,
        )
        six_mode = False
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

    items_full_catalog = bundle.items
    only_ids = _parse_only_champions_csv(args.only_champions)
    ref_champs = REFERENCE if not offline else (("generic_ap", FarmMode.LANE, True),)
    champs = tuple(c for c in ref_champs if only_ids is None or c[0] in only_ids)
    if not champs:
        print(
            "--only-champions did not match any of lux, quinn, karthus (or generic_ap offline).",
            file=sys.stderr,
        )
        sys.exit(1)

    ex_tags = _parse_item_tag_csv(args.exclude_item_tags)
    rq_tags = _parse_item_tag_csv(args.require_item_tags)

    def build_item_catalog_for_champion(farm_mode: FarmMode, champion_id: str) -> dict[str, ItemDef]:
        from LoLPerfmon.sim.kit_stat_alignment import filter_waveclear_catalog_stat_aligned as _stat_cat

        if args.no_waveclear_heuristics:
            cat = dict(items_full_catalog)
            if ex_tags or rq_tags:
                cat = filter_items_by_tags(cat, exclude_tags=ex_tags, require_tags=rq_tags)
        else:
            merged_ex = DEFAULT_WAVECLEAR_EXCLUDE_TAGS | ex_tags
            rq = rq_tags if rq_tags else None
            if args.stat_align_waveclear and champion_id in bundle.champions:
                cat = _stat_cat(
                    items_full_catalog,
                    farm_mode,
                    bundle.champions[champion_id],
                    exclude_tags=merged_ex,
                    require_tags=rq,
                    level=args.stat_align_level,
                )
            else:
                cat = filter_waveclear_item_catalog(
                    items_full_catalog, farm_mode, exclude_tags=merged_ex, require_tags=rq
                )
        if farm_mode == FarmMode.JUNGLE:
            merged = dict(cat)
            for iid, it in items_full_catalog.items():
                if is_jungle_companion_item(it):
                    merged[iid] = it
            cat = merged
        return cat

    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    if six_mode:
        t_sim = float("inf")
        extrap = True
        t_note = (
            f"inf (stop at 6 build-endpoint items or {args.six_terminal_max_seconds:.0f}s simulated clock)"
        )
    else:
        t_sim = args.t_max
        # Finite horizons beyond the precomputed wave list need synthetic waves (see simulate).
        extrap = True
        t_note = f"{args.t_max:.0f}s"

    lines: list[str] = [
        "LoLPerfmon — modeled farm / waveclear build (gameplay reference, not live-client optimal).",
        f"patch={bundle.rules.patch_version}",
        f"search: beam_depth={args.beam_depth} beam_width={args.beam_width} max_leaf_evals={args.max_leaf_evals} "
        f"t_max={t_note} marginal_objective={marginal_objective} leaf_score={args.leaf_score} "
        f"six_terminal_items={six_mode}",
        f"waveclear_heuristics={'off' if args.no_waveclear_heuristics else 'on'}",
    ]
    if not args.no_waveclear_heuristics:
        merged_ex_line = sorted(DEFAULT_WAVECLEAR_EXCLUDE_TAGS | ex_tags)
        lines.append(f"waveclear_default_exclude_tags (merged with --exclude-item-tags)={merged_ex_line}")
    lines.append(f"stat_align_waveclear={args.stat_align_waveclear} stat_align_level={args.stat_align_level}")
    if ex_tags or rq_tags:
        lines.append(
            f"item_catalog_filter exclude_tags={sorted(ex_tags)} require_tags={sorted(rq_tags)}"
        )
    if args.leaf_score == "early_dps_auc":
        lines.append(f"early_dps_auc: integral of modeled effective DPS over [0, {args.early_horizon_seconds:.0f}]s game time")
    elif args.leaf_score == "total_clear_units":
        lines.append(
            "total_clear_units: maximize total_lane_minions_cleared (lane) or total_jungle_monsters_cleared (jungle); "
            "this script sets marginal_income_cap=True for jungle so clear-tick marginals apply. "
            f"Empty-prefix marginal_objective={marginal_objective} (Δprimary units: clears for leaf; gold for total_farm_gold)."
        )
    lines.extend(
        [
            "lane: marginal_income_cap=True (capped-throughput marginal). "
            "jungle: marginal_income_cap=False unless leaf_score=total_clear_units (then True).",
        ]
    )
    if six_mode:
        lines.append(
            "six_terminal_items: greedy marginals use endpoints_only_marginals "
            "(no standalone Long Sword / Tome / …); recipe combines run before each buy wave."
        )
    lines.append("")
    if only_ids is not None:
        lines.append(f"only_champions={sorted(only_ids)}")

    for cid, farm_mode, marginal_cap in champs:
        if args.leaf_score == "total_clear_units":
            marginal_cap = True
        if cid not in bundle.champions:
            lines.append(f"# skip {cid}: not in bundle")
            lines.append("")
            continue
        filtered_items = build_item_catalog_for_champion(farm_mode, cid)
        if not filtered_items:
            lines.append(
                f"# skip {cid}: empty item catalog after filters; relax tags or use --no-waveclear-heuristics"
            )
            lines.append("")
            continue
        champ_bundle = replace(bundle, items=filtered_items)
        if six_mode:
            early = _six_endpoints_or_max_clock(champ_bundle.items, args.six_terminal_max_seconds)
        else:
            early = None
        if farm_mode == FarmMode.JUNGLE:
            best = None
            best_sid: str | None = None
            for sid in jungle_pet_companion_item_ids_sorted(champ_bundle):
                pack = beam_refined_farm_build(
                    champ_bundle,
                    cid,
                    t_max=t_sim,
                    beam_width=args.beam_width,
                    beam_depth=args.beam_depth,
                    max_leaf_evals=args.max_leaf_evals,
                    farm_mode=farm_mode,
                    marginal_objective=marginal_objective,
                    horizon_candidate_cap=args.horizon_candidate_cap,
                    jungle_starter_item_id=sid,
                    marginal_income_cap=marginal_cap,
                    leaf_score=args.leaf_score,
                    early_horizon_seconds=args.early_horizon_seconds,
                    early_stop=early,
                    extrapolate_lane_waves=extrap,
                    endpoints_only_marginals=six_mode,
                )
                if best is None or pack[1] > best[1]:
                    best = pack
                    best_sid = sid
            assert best is not None and best_sid is not None
            order, primary_score, res_best, meta = best
            starter_name = champ_bundle.items[best_sid].name if best_sid in champ_bundle.items else best_sid
        else:
            order, primary_score, res_best, meta = beam_refined_farm_build(
                champ_bundle,
                cid,
                t_max=t_sim,
                beam_width=args.beam_width,
                beam_depth=args.beam_depth,
                max_leaf_evals=args.max_leaf_evals,
                farm_mode=farm_mode,
                marginal_objective=marginal_objective,
                horizon_candidate_cap=args.horizon_candidate_cap,
                marginal_income_cap=marginal_cap,
                leaf_score=args.leaf_score,
                early_horizon_seconds=args.early_horizon_seconds,
                early_stop=early,
                extrapolate_lane_waves=extrap,
                endpoints_only_marginals=six_mode,
            )
            starter_name = None

        names = [champ_bundle.items[i].name if i in champ_bundle.items else i for i in order]
        lines.append(f"=== {cid.upper()} ({farm_mode.value}) ===")
        if starter_name:
            lines.append(f"jungle_starter: {starter_name}")
        if args.leaf_score == "early_dps_auc":
            lines.append(f"leaf_metric early_dps_auc (∫ DPS dt to {args.early_horizon_seconds:.0f}s): {primary_score:.4f}")
        elif args.leaf_score == "farm_gold_per_gold_spent":
            lines.append(f"leaf_metric farm_gold_per_gold_spent: {primary_score:.6f}")
        elif args.leaf_score == "total_clear_units":
            lines.append(
                f"leaf_metric total_clear_units: {primary_score:.4f} "
                f"(lane_minions={res_best.total_lane_minions_cleared:.4f} "
                f"monsters={res_best.total_jungle_monsters_cleared:.4f})"
            )
        else:
            lines.append(f"leaf_metric total_farm_gold (full sim to t_max): {primary_score:.2f}")
        lines.append(f"total_farm_gold same run (reference): {res_best.total_farm_gold:.2f}")
        gb = gold_income_breakdown(res_best)
        income_gross = (
            gb["total_farm_gold"] + gb["total_passive_gold"] + gb["total_shop_sell_gold"]
        )
        lines.append(
            "gold_income_breakdown: "
            f"farm_ticks={gb['total_farm_gold']:.2f} passive={gb['total_passive_gold']:.2f} "
            f"shop_sells={gb['total_shop_sell_gold']:.2f} (farm+passive+sells_sum={income_gross:.2f})"
        )
        if income_gross > 1e-9:
            fp = 100.0 * gb["total_farm_gold"] / income_gross
            pp = 100.0 * gb["total_passive_gold"] / income_gross
            sp = 100.0 * gb["total_shop_sell_gold"] / income_gross
            lines.append(
                f"gold_income_shares_pct: farm_ticks={fp:.1f}% passive={pp:.1f}% shop_sells={sp:.1f}%"
            )
        lines.append(
            "gold_flow: "
            f"starting={gb['starting_gold']:.2f} spent_on_items={gb['total_gold_spent_on_items']:.2f} "
            f"final_wallet={gb['final_gold']:.2f} net_wealth_delta={gb['net_wealth_delta']:.2f}"
        )
        rec_err = gold_flow_reconciliation_error(res_best)
        lines.append(
            f"gold_flow_reconciliation_abs_error={rec_err:.2e} (expect ~0; start+farm+passive+sells-spent=final)"
        )
        if args.leaf_score == "total_clear_units":
            lines.append(
                f"default_clear_count_score check: {default_clear_count_score(res_best, farm_mode):.4f}"
            )
        lines.append(f"sim ended_by_early_stop: {res_best.ended_by_early_stop}")
        lines.append(f"meta: {meta}")
        prof = bundle.champions[cid]
        ax, ap_c, ad_c = infer_primary_ability_damage_axis(prof, level=args.stat_align_level)
        lines.append(
            f"inferred_primary_ability_axis={ax} dominant_line_ap_coeff={ap_c:.6g} "
            f"dominant_line_ad_coeff={ad_c:.6g} (level={args.stat_align_level} spell rank)"
        )
        if args.stat_align_waveclear or args.print_modeled_dps_steps:
            steps = marginal_dps_along_build_order(
                prof, tuple(order), champ_bundle.items, level=args.stat_align_level
            )
            lines.append(
                "modeled_effective_dps_per_step (fixed level, sticker-cost ratio; not farm tick / gold sim):"
            )
            for row in steps:
                lines.append(
                    f"  step {row['step']}: {row['item_id']}  Δdps={row['delta_dps']:.4f} "
                    f"Δdps/item_sticker_cost={row['delta_dps_per_item_total_cost']:.6f}  dps_after={row['dps_after']:.4f}"
                )
        if six_mode:
            fin = res_best.final_inventory
            all_ep = all(is_build_endpoint_item(champ_bundle.items[i]) for i in fin if i in champ_bundle.items)
            lines.append(
                f"final_inventory ({len(fin)} slots): all DD endpoints (into empty) = {all_ep}"
            )
            if res_best.ended_by_early_stop:
                if len(fin) == 6 and all_ep:
                    lines.append("six_terminal_stop: achieved 6 items with no further shop upgrades (Data Dragon into empty).")
                elif len(fin) < 6:
                    lines.append(
                        f"six_terminal_stop: hit --six-terminal-max-seconds with only {len(fin)} items; "
                        "raise that cap or use a larger beam budget."
                    )
                else:
                    lines.append(
                        "six_terminal_stop: hit --six-terminal-max-seconds before every slot was a DD endpoint "
                        "(many items still list upgrades in into, e.g. Amplifying Tome, NLR; raise cap or accept longer sims)."
                    )
            for i, oid in enumerate(fin, 1):
                nm = champ_bundle.items[oid].name if oid in champ_bundle.items else oid
                ep = (
                    is_build_endpoint_item(champ_bundle.items[oid])
                    if oid in champ_bundle.items
                    else False
                )
                lines.append(f"  slot {i}: {nm}  [{oid}]  endpoint={ep}")
        lines.append("purchase_sequence (greedy acquisition order; name, Data Dragon id):")
        for i, (n, oid) in enumerate(zip(names, order, strict=True), 1):
            lines.append(f"  {i}. {n}  [{oid}]")
        if not names:
            lines.append("  (none)")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
