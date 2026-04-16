from __future__ import annotations

import pytest

from LoLPerfmon.data.loaders import data_root_default, load_bundle
from LoLPerfmon.sim.config import DEFAULT_JUNGLER_STARTER_ITEM_ID, DEFAULT_LANER_STARTER_ITEM_ID, FarmMode
from LoLPerfmon.sim.runner import farm_mode_from_role, resolve_item_id, resolve_starter_item_id


def test_farm_mode_from_role() -> None:
    assert farm_mode_from_role("laner") == FarmMode.LANE
    assert farm_mode_from_role("jungler") == FarmMode.JUNGLE
    with pytest.raises(ValueError):
        farm_mode_from_role("mid")


def test_resolve_item_id_by_name() -> None:
    root = data_root_default()
    _, items, _, _ = load_bundle(root)
    assert resolve_item_id("amplifying_tome", items) == "amplifying_tome"
    assert resolve_item_id("Amplifying Tome", items) == "amplifying_tome"


def test_resolve_starter_defaults() -> None:
    root = data_root_default()
    _, items, _, _ = load_bundle(root)
    laner = resolve_starter_item_id(FarmMode.LANE, None, no_starter=False, items_catalog=items)
    assert laner == DEFAULT_LANER_STARTER_ITEM_ID
    jung = resolve_starter_item_id(FarmMode.JUNGLE, None, no_starter=False, items_catalog=items)
    assert jung == DEFAULT_JUNGLER_STARTER_ITEM_ID
    assert resolve_starter_item_id(FarmMode.LANE, None, no_starter=True, items_catalog=items) is None
