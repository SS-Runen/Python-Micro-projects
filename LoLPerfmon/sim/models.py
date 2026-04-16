from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from LoLPerfmon.sim.config import FarmMode, MAX_INVENTORY_SLOTS


@dataclass(frozen=True)
class SourceProvenance:
    source_name: str
    source_url: str = ""
    fetched_at: str = ""
    patch_hint: str = ""
    parser_version: str = ""
    confidence: float = 1.0
    checksum: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")


@dataclass(frozen=True)
class DiscrepancyRecord:
    entity_type: str
    entity_id: str
    field_path: str
    canonical_value: Any
    candidate_value: Any
    source_name: str
    delta_kind: Literal["identity_mismatch", "numeric_drift", "schema_gap", "missing"]
    severity: Literal["low", "medium", "high"]
    resolution_status: Literal["open", "accepted_wiki", "accepted_ddragon", "override"] = "open"


@dataclass(frozen=True)
class ChampionStatic:
    champion_id: str
    name: str
    role_modes_allowed: tuple[FarmMode, ...]
    base_stats_at_level1: dict[str, float]
    growth_per_level: dict[str, float]
    ability_scaling_profile: dict[str, Any] = field(default_factory=dict)
    clear_profile_tags: tuple[str, ...] = ()
    source_provenance: SourceProvenance | None = None

    def __post_init__(self) -> None:
        if not self.champion_id:
            raise ValueError("champion_id required")
        if not self.base_stats_at_level1:
            raise ValueError("base_stats_at_level1 must be non-empty")


@dataclass(frozen=True)
class ItemStatic:
    item_id: str
    name: str
    cost: float
    stats_granted: dict[str, float]
    passive_tags: tuple[str, ...] = ()
    builds_from: tuple[str, ...] = ()
    builds_into: tuple[str, ...] = ()
    slot_cost: int = 1
    is_jungle_starter: bool = False
    source_provenance: SourceProvenance | None = None

    def __post_init__(self) -> None:
        if self.cost < 0:
            raise ValueError("cost must be >= 0")
        if self.slot_cost < 1:
            raise ValueError("slot_cost must be >= 1")


@dataclass(frozen=True)
class AbilityStatic:
    champion_id: str
    spell_slot: str
    base_damage_by_rank: tuple[float, ...] = ()
    scaling_terms: tuple[dict[str, float], ...] = ()
    resource_cost_by_rank: tuple[float, ...] = ()
    cooldown_by_rank: tuple[float, ...] = ()
    aoe_profile: str = "single"
    targeting_type: str = "skillshot"
    tags: tuple[str, ...] = ()
    source_provenance: SourceProvenance | None = None


@dataclass(frozen=True)
class UnitStatic:
    unit_id: str
    unit_class: str
    spawn_rules: dict[str, Any]
    base_hp_armor_mr: dict[str, float]
    growth_rules: dict[str, Any] = field(default_factory=dict)
    gold_xp_reward: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.unit_id:
            raise ValueError("unit_id required")


@dataclass
class RecipeGraph:
    parents_by_item: dict[str, tuple[str, ...]]
    children_by_item: dict[str, tuple[str, ...]]
    full_cost_by_item: dict[str, float]

    def __post_init__(self) -> None:
        for iid, cost in self.full_cost_by_item.items():
            if cost < 0:
                raise ValueError(f"full_cost negative for {iid}")


@dataclass
class GameState:
    time_sec: float
    mode: FarmMode
    gold_wallet: float
    xp: float
    level: int
    inventory_slots: list[str | None]
    completed_item_ids: tuple[str, ...] = ()
    components_held: dict[str, int] = field(default_factory=dict)
    spawn_state: dict[str, Any] = field(default_factory=dict)
    farm_counters: dict[str, float] = field(default_factory=dict)
    passive_gold_accrued: float = 0.0
    gold_spent: float = 0.0

    def __post_init__(self) -> None:
        if len(self.inventory_slots) != MAX_INVENTORY_SLOTS:
            raise ValueError(f"inventory must have {MAX_INVENTORY_SLOTS} slots")
        if self.gold_wallet < 0:
            raise ValueError("gold_wallet must be >= 0")
        if self.level < 1:
            raise ValueError("level must be >= 1")


@dataclass
class DerivedCombatState:
    effective_stats: dict[str, float]
    lane_dps: float = 0.0
    jungle_dps: float = 0.0


@dataclass
class SearchNode:
    state_hash: str
    parent_ref: str | None
    last_action: str | None
    cum_score: float
    heuristic_upper_bound: float
    depth: int
    milestone_metrics: dict[str, float] = field(default_factory=dict)


def validate_champion(c: ChampionStatic) -> None:
    _ = c


def validate_item(i: ItemStatic) -> None:
    _ = i


def validate_recipe_graph(items: dict[str, ItemStatic], graph: RecipeGraph) -> None:
    for iid in graph.full_cost_by_item:
        if iid not in items:
            raise ValueError(f"full_cost references unknown item {iid}")
    for parent, children in graph.children_by_item.items():
        if parent not in items:
            raise ValueError(f"recipe parent unknown: {parent}")
        for c in children:
            if c not in items:
                raise ValueError(f"recipe child unknown: {c}")


def level_stats(champ: ChampionStatic, level: int) -> dict[str, float]:
    if level < 1:
        raise ValueError("level >= 1")
    out: dict[str, float] = {}
    for k, base in champ.base_stats_at_level1.items():
        growth = champ.growth_per_level.get(k, 0.0)
        out[k] = base + growth * float(level - 1)
    return out
