from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from .spell_farm_model import SpellFarmCoefficients


@dataclass(frozen=True)
class ItemDef:
    id: str
    name: str
    total_cost: float
    stats: "StatBonus"
    from_ids: tuple[str, ...] = field(default_factory=tuple)
    #: Data Dragon ``into`` — ids this item upgrades into; empty means **build endpoint** (no further upgrades).
    into_ids: tuple[str, ...] = field(default_factory=tuple)
    #: Data Dragon ``tags`` (e.g. ``Boots``) for shop compatibility checks.
    tags: tuple[str, ...] = field(default_factory=tuple)
    #: Max copies of this item id in inventory (League: one terminal legendary, one Seal, many Daggers).
    max_inventory_copies: int = 6


def is_build_endpoint_item(it: ItemDef) -> bool:
    """True if Data Dragon ``into`` is empty — no further shop upgrades from this item."""
    return len(it.into_ids) == 0


@dataclass(frozen=True)
class StatBonus:
    attack_damage: float = 0.0
    ability_power: float = 0.0
    bonus_attack_speed_fraction: float = 0.0
    ability_haste: float = 0.0
    health: float = 0.0
    mana: float = 0.0
    armor: float = 0.0
    magic_resist: float = 0.0


@dataclass(frozen=True)
class KitParams:
    """Weights for lane/jungle farm DPS; see :func:`LoLPerfmon.sim.clear.lane_clear_dps`."""

    ad_weight: float = 1.0
    ap_weight: float = 1.0
    as_weight: float = 0.5
    ah_weight: float = 0.02
    base_ability_dps: float = 0.0
    #: Multiplier on ``attack_speed * attack_damage`` (auto-based clear). Use ``0`` for
    #: champions modeled as **waveclearing with abilities only** (e.g. typical mages).
    auto_attack_clear_weight: float = 1.0


@dataclass(frozen=True)
class ChampionProfile:
    id: str
    base_health: float
    growth_health: float
    base_mana: float
    growth_mana: float
    base_attack_damage: float
    growth_attack_damage: float
    base_ability_power: float
    growth_ability_power: float
    base_armor: float
    growth_armor: float
    base_magic_resist: float
    growth_magic_resist: float
    base_attack_speed: float
    attack_speed_ratio: float
    bonus_attack_speed_growth: float
    kit: KitParams = field(default_factory=KitParams)
    spell_farm: "SpellFarmCoefficients | None" = None

    @staticmethod
    def from_json(obj: Mapping[str, Any]) -> ChampionProfile:
        kit_raw = obj.get("kit") or {}
        kit = KitParams(
            ad_weight=float(kit_raw.get("ad_weight", 1.0)),
            ap_weight=float(kit_raw.get("ap_weight", 1.0)),
            as_weight=float(kit_raw.get("as_weight", 0.5)),
            ah_weight=float(kit_raw.get("ah_weight", 0.02)),
            base_ability_dps=float(kit_raw.get("base_ability_dps", 0.0)),
            auto_attack_clear_weight=float(kit_raw.get("auto_attack_clear_weight", 1.0)),
        )
        return ChampionProfile(
            id=str(obj["id"]),
            base_health=float(obj["base_health"]),
            growth_health=float(obj["growth_health"]),
            base_mana=float(obj["base_mana"]),
            growth_mana=float(obj["growth_mana"]),
            base_attack_damage=float(obj["base_attack_damage"]),
            growth_attack_damage=float(obj["growth_attack_damage"]),
            base_ability_power=float(obj.get("base_ability_power", 0.0)),
            growth_ability_power=float(obj.get("growth_ability_power", 0.0)),
            base_armor=float(obj["base_armor"]),
            growth_armor=float(obj["growth_armor"]),
            base_magic_resist=float(obj["base_magic_resist"]),
            growth_magic_resist=float(obj["growth_magic_resist"]),
            base_attack_speed=float(obj["base_attack_speed"]),
            attack_speed_ratio=float(obj["attack_speed_ratio"]),
            bonus_attack_speed_growth=float(obj["bonus_attack_speed_growth"]),
            kit=kit,
            spell_farm=None,
        )


def load_items_from_json(items_list: list[Mapping[str, Any]]) -> dict[str, ItemDef]:
    out: dict[str, ItemDef] = {}
    for raw in items_list:
        st = raw["stats"]
        bonus = StatBonus(
            attack_damage=float(st.get("attack_damage", 0)),
            ability_power=float(st.get("ability_power", 0)),
            bonus_attack_speed_fraction=float(st.get("bonus_attack_speed_fraction", 0)),
            ability_haste=float(st.get("ability_haste", 0)),
            health=float(st.get("health", 0)),
            mana=float(st.get("mana", 0)),
            armor=float(st.get("armor", 0)),
            magic_resist=float(st.get("magic_resist", 0)),
        )
        fid = raw.get("from_ids")
        if isinstance(fid, (list, tuple)):
            from_ids = tuple(str(x) for x in fid)
        else:
            from_ids = ()
        iid = raw.get("into_ids")
        if isinstance(iid, (list, tuple)):
            into_ids = tuple(str(x) for x in iid)
        else:
            into_ids = ()
        mic = int(raw.get("max_inventory_copies", 6))
        tr = raw.get("tags")
        if isinstance(tr, (list, tuple)):
            tags = tuple(str(x) for x in tr)
        else:
            tags = ()
        out[str(raw["id"])] = ItemDef(
            id=str(raw["id"]),
            name=str(raw["name"]),
            total_cost=float(raw["total_cost"]),
            stats=bonus,
            from_ids=from_ids,
            into_ids=into_ids,
            tags=tags,
            max_inventory_copies=mic,
        )
    return out
