from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from LoLPerfmon.sim.models import (
    AbilityStatic,
    ChampionStatic,
    ItemStatic,
    RecipeGraph,
    SourceProvenance,
    UnitStatic,
    validate_recipe_graph,
)
from LoLPerfmon.sim.config import FarmMode


def _provenance(d: dict[str, Any] | None) -> SourceProvenance | None:
    if not d:
        return None
    return SourceProvenance(
        source_name=str(d.get("source_name", "bundled")),
        source_url=str(d.get("source_url", "")),
        fetched_at=str(d.get("fetched_at", "")),
        patch_hint=str(d.get("patch_hint", "")),
        parser_version=str(d.get("parser_version", "")),
        confidence=float(d.get("confidence", 1.0)),
        checksum=str(d.get("checksum", "")),
    )


def load_champion(path: Path) -> ChampionStatic:
    raw = json.loads(path.read_text(encoding="utf-8"))
    modes = tuple(FarmMode(m) for m in raw["role_modes_allowed"])
    return ChampionStatic(
        champion_id=raw["champion_id"],
        name=raw["name"],
        role_modes_allowed=modes,
        base_stats_at_level1=dict(raw["base_stats_at_level1"]),
        growth_per_level=dict(raw["growth_per_level"]),
        ability_scaling_profile=dict(raw.get("ability_scaling_profile", {})),
        clear_profile_tags=tuple(raw.get("clear_profile_tags", [])),
        source_provenance=_provenance(raw.get("source_provenance")),
    )


def load_item(path: Path) -> ItemStatic:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ItemStatic(
        item_id=raw["item_id"],
        name=raw["name"],
        cost=float(raw["cost"]),
        stats_granted=dict(raw.get("stats_granted", {})),
        passive_tags=tuple(raw.get("passive_tags", [])),
        builds_from=tuple(raw.get("builds_from", [])),
        builds_into=tuple(raw.get("builds_into", [])),
        slot_cost=int(raw.get("slot_cost", 1)),
        is_jungle_starter=bool(raw.get("is_jungle_starter", False)),
        source_provenance=_provenance(raw.get("source_provenance")),
    )


def load_unit(path: Path) -> UnitStatic:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return UnitStatic(
        unit_id=raw["unit_id"],
        unit_class=raw["unit_class"],
        spawn_rules=dict(raw["spawn_rules"]),
        base_hp_armor_mr=dict(raw["base_hp_armor_mr"]),
        growth_rules=dict(raw.get("growth_rules", {})),
        gold_xp_reward=dict(raw.get("gold_xp_reward", {})),
    )


def load_ability(path: Path) -> AbilityStatic:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return AbilityStatic(
        champion_id=raw["champion_id"],
        spell_slot=raw["spell_slot"],
        base_damage_by_rank=tuple(raw.get("base_damage_by_rank", [])),
        scaling_terms=tuple(dict(x) for x in raw.get("scaling_terms", [])),
        resource_cost_by_rank=tuple(raw.get("resource_cost_by_rank", [])),
        cooldown_by_rank=tuple(raw.get("cooldown_by_rank", [])),
        aoe_profile=str(raw.get("aoe_profile", "single")),
        targeting_type=str(raw.get("targeting_type", "skillshot")),
        tags=tuple(raw.get("tags", [])),
        source_provenance=_provenance(raw.get("source_provenance")),
    )


def load_items_dir(items_dir: Path) -> dict[str, ItemStatic]:
    out: dict[str, ItemStatic] = {}
    if not items_dir.is_dir():
        return out
    for p in sorted(items_dir.glob("*.json")):
        it = load_item(p)
        out[it.item_id] = it
    return out


def load_champions_dir(ch_dir: Path) -> dict[str, ChampionStatic]:
    out: dict[str, ChampionStatic] = {}
    if not ch_dir.is_dir():
        return out
    for p in sorted(ch_dir.glob("*.json")):
        c = load_champion(p)
        out[c.champion_id] = c
    return out


def build_recipe_graph(items: dict[str, ItemStatic]) -> RecipeGraph:
    parents: dict[str, list[str]] = {}
    children: dict[str, list[str]] = {}
    full_cost: dict[str, float] = {}
    for iid, it in items.items():
        full_cost[iid] = it.cost
        for child in it.builds_into:
            parents.setdefault(child, []).append(iid)
        for comp in it.builds_from:
            children.setdefault(iid, []).append(comp)
    return RecipeGraph(
        parents_by_item={k: tuple(v) for k, v in parents.items()},
        children_by_item={k: tuple(v) for k, v in children.items()},
        full_cost_by_item=full_cost,
    )


def load_bundle(data_root: Path) -> tuple[dict[str, ChampionStatic], dict[str, ItemStatic], dict[str, UnitStatic], RecipeGraph]:
    ch = load_champions_dir(data_root / "champions")
    items = load_items_dir(data_root / "items")
    units: dict[str, UnitStatic] = {}
    mdir = data_root / "minions"
    if mdir.is_dir():
        for p in mdir.glob("*.json"):
            u = load_unit(p)
            units[u.unit_id] = u
    jdir = data_root / "monsters"
    if jdir.is_dir():
        for p in jdir.glob("*.json"):
            u = load_unit(p)
            units[u.unit_id] = u
    graph = build_recipe_graph(items)
    validate_recipe_graph(items, graph)
    return ch, items, units, graph


def data_root_default() -> Path:
    return Path(__file__).resolve().parent
