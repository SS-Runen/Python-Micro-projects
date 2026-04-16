from __future__ import annotations

from dataclasses import dataclass

from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.models import ChampionStatic, ItemStatic, UnitStatic
from LoLPerfmon.sim.simulator import SimResult, simulate_with_buy_order


@dataclass(frozen=True)
class BeamSearchConfig:
    beam_width: int = 8
    max_depth: int = 6
    max_leaf_evals: int = 256
    t_max: float = 600.0


def beam_search_farm_build(
    champ: ChampionStatic,
    mode: FarmMode,
    items_catalog: dict[str, ItemStatic],
    candidate_ids: tuple[str, ...],
    *,
    lane_minion: UnitStatic | None,
    jungle_monster: UnitStatic | None,
    cfg: BeamSearchConfig | None = None,
    leaf_score: str = "total_farm_gold",
) -> tuple[tuple[str, ...], float, SimResult]:
    cfg = cfg or BeamSearchConfig()
    if mode == FarmMode.LANE and lane_minion is None:
        raise ValueError("lane_minion required")
    if mode == FarmMode.JUNGLE and jungle_monster is None:
        raise ValueError("jungle_monster required")

    def score(res: SimResult) -> float:
        if leaf_score == "total_clear_units":
            if mode == FarmMode.LANE:
                return res.total_lane_minions_cleared
            return res.total_jungle_monsters_cleared
        return res.total_farm_gold

    leaves_evaluated = 0
    best: tuple[tuple[str, ...], float, SimResult] | None = None

    def eval_prefix(prefix: tuple[str, ...]) -> SimResult:
        nonlocal leaves_evaluated
        leaves_evaluated += 1
        # Prefixes may list a completed item after its components; the simulator
        # resolves recipe combine when inventory holds builds_from.
        return simulate_with_buy_order(
            champ,
            mode,
            items_catalog,
            prefix,
            cfg.t_max,
            lane_minion=lane_minion,
            jungle_monster=jungle_monster,
        )

    def consider(prefix: tuple[str, ...], res: SimResult) -> None:
        nonlocal best
        s = score(res)
        if best is None or s > best[1]:
            best = (prefix, s, res)

    if leaves_evaluated < cfg.max_leaf_evals:
        empty_res = eval_prefix(())
        consider((), empty_res)

    frontier: list[tuple[str, ...]] = [()]
    for _ in range(cfg.max_depth):
        if leaves_evaluated >= cfg.max_leaf_evals:
            break
        expanded: list[tuple[tuple[str, ...], float, SimResult]] = []
        for prefix in frontier:
            if leaves_evaluated >= cfg.max_leaf_evals:
                break
            for nxt in candidate_ids:
                if nxt not in items_catalog:
                    continue
                if leaves_evaluated >= cfg.max_leaf_evals:
                    break
                child = prefix + (nxt,)
                res = eval_prefix(child)
                expanded.append((child, score(res), res))
                consider(child, res)
        expanded.sort(key=lambda x: x[1], reverse=True)
        frontier = [p for p, _, _ in expanded[: cfg.beam_width]]
        if not frontier:
            break

    if best is None:
        res = simulate_with_buy_order(
            champ,
            mode,
            items_catalog,
            (),
            cfg.t_max,
            lane_minion=lane_minion,
            jungle_monster=jungle_monster,
        )
        return (), score(res), res
    return best


def dominance_prune_prefixes(
    scored: list[tuple[tuple[str, ...], float]],
) -> list[tuple[tuple[str, ...], float]]:
    if not scored:
        return []
    scored_sorted = sorted(scored, key=lambda x: x[1], reverse=True)
    return scored_sorted[: max(1, len(scored_sorted) // 2 or 1)]
