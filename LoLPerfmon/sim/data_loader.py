from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .models import ChampionProfile, ItemDef, load_items_from_json


def _interp_bracket(value: float, table: Mapping[str, float]) -> float:
    keys = sorted(float(k) for k in table)
    if not keys:
        return 0.0
    if value <= keys[0]:
        return float(table[str(int(keys[0]))])
    if value >= keys[-1]:
        return float(table[str(int(keys[-1]))])
    for i in range(len(keys) - 1):
        a, b = keys[i], keys[i + 1]
        if a <= value <= b:
            va = float(table[str(int(a))])
            vb = float(table[str(int(b))])
            t = (value - a) / (b - a) if b > a else 0.0
            return va + t * (vb - va)
    return float(table[str(int(keys[-1]))])


@dataclass(frozen=True)
class WaveComposition:
    wave_index: int
    melee: int
    caster: int
    siege: int


def wave_minion_count(wave: WaveComposition) -> int:
    """Total lane minions in one wave composition (deterministic model; no cannon RNG)."""
    return wave.melee + wave.caster + wave.siege


@dataclass(frozen=True)
class GameRules:
    patch_version: str
    first_wave_spawn_seconds: float
    wave_interval_seconds: float
    passive_gold_per_10_seconds: float
    passive_gold_start_seconds: float
    start_gold: float
    xp_to_next_level: tuple[int, ...]
    minion_xp_melee_by_level: tuple[float, ...]
    minion_xp_caster_by_level: tuple[float, ...]
    minion_xp_siege_by_level: tuple[float, ...]
    jungle_base_cycle_seconds: float
    jungle_base_route_gold: float
    jungle_base_route_xp: float
    #: Abstract monsters cleared per full route at ``eff=1`` (scale ``eff`` each cycle).
    jungle_monsters_per_route: float = 1.0
    #: Seconds per wave cycle not available for applying DPS to the wave (spawn/path/range abstraction).
    lane_engagement_overhead_seconds: float = 0.0
    #: Extra seconds before a jungle route clear completes (pathing/range abstraction).
    jungle_engagement_overhead_seconds: float = 0.0


@dataclass
class GameDataBundle:
    rules: GameRules
    champions: dict[str, ChampionProfile]
    items: dict[str, ItemDef]
    waves: list[WaveComposition]
    minion_economy: Mapping[str, Any]
    data_dir: Path | None

    def gold_for_kill(self, minion_type: str, game_minute: float) -> float:
        block = self.minion_economy[minion_type]["gold_per_kill"]
        return _interp_bracket(game_minute, {k: float(v) for k, v in block.items()})

    def hp_for_minion(self, minion_type: str, game_minute: float) -> float:
        block = self.minion_economy[minion_type]["hp"]
        return _interp_bracket(game_minute, {k: float(v) for k, v in block.items()})

    def wave_at_index(self, wave_index: int) -> WaveComposition | None:
        for w in self.waves:
            if w.wave_index == wave_index:
                return w
        return None

    def cumulative_cs_by_wave_index(self) -> dict[int, int]:
        """Max lane CS if every minion in waves 0..k is last-hit (derived from composition)."""
        out: dict[int, int] = {}
        total = 0
        for w in self.waves:
            total += w.melee + w.caster + w.siege
            out[w.wave_index] = total
        return out


def cumulative_xp_thresholds(xp_to_next: tuple[int, ...]) -> tuple[float, ...]:
    out: list[float] = [0.0]
    s = 0.0
    for x in xp_to_next:
        s += float(x)
        out.append(s)
    return tuple(out)


def load_game_data_from_dicts(
    data_dir: Path | None,
    game: Mapping[str, Any],
    waves_raw: Mapping[str, Any],
    items_raw: list[Mapping[str, Any]],
    champs_raw: list[Mapping[str, Any]],
) -> GameDataBundle:
    rules = GameRules(
        patch_version=str(game["patch_version"]),
        first_wave_spawn_seconds=float(game["first_wave_spawn_seconds"]),
        wave_interval_seconds=float(game["wave_interval_seconds"]),
        passive_gold_per_10_seconds=float(game["passive_gold_per_10_seconds"]),
        passive_gold_start_seconds=float(game["passive_gold_start_seconds"]),
        start_gold=float(game["start_gold"]),
        xp_to_next_level=tuple(int(x) for x in game["xp_to_next_level"]),
        minion_xp_melee_by_level=tuple(float(x) for x in game["minion_xp_melee_by_level"]),
        minion_xp_caster_by_level=tuple(float(x) for x in game["minion_xp_caster_by_level"]),
        minion_xp_siege_by_level=tuple(float(x) for x in game["minion_xp_siege_by_level"]),
        jungle_base_cycle_seconds=float(game["jungle"]["base_cycle_seconds"]),
        jungle_base_route_gold=float(game["jungle"]["base_route_gold"]),
        jungle_base_route_xp=float(game["jungle"]["base_route_xp"]),
        jungle_monsters_per_route=float(game["jungle"].get("monsters_per_route", 1.0)),
        lane_engagement_overhead_seconds=float(game.get("lane_engagement_overhead_seconds", 0.0)),
        jungle_engagement_overhead_seconds=float(
            game.get("jungle_engagement_overhead_seconds", 0.0)
        ),
    )
    waves = [
        WaveComposition(
            wave_index=int(w["wave_index"]),
            melee=int(w["melee"]),
            caster=int(w["caster"]),
            siege=int(w["siege"]),
        )
        for w in waves_raw["waves"]
    ]
    champs = {c["id"]: ChampionProfile.from_json(c) for c in champs_raw}
    items = load_items_from_json(items_raw)
    return GameDataBundle(
        rules=rules,
        champions=champs,
        items=items,
        waves=waves,
        minion_economy=waves_raw["minion_types"],
        data_dir=data_dir,
    )


def load_game_data(data_dir: Path | str) -> GameDataBundle:
    """Load bundle from a directory of JSON files (optional advanced use)."""
    root = Path(data_dir)
    with (root / "game.json").open(encoding="utf-8") as f:
        game = json.load(f)
    with (root / "waves.json").open(encoding="utf-8") as f:
        waves_raw = json.load(f)
    with (root / "items.json").open(encoding="utf-8") as f:
        items_raw = json.load(f)
    with (root / "champions.json").open(encoding="utf-8") as f:
        champs_raw = json.load(f)
    return load_game_data_from_dicts(root, game, waves_raw, items_raw, champs_raw)
