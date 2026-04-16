import pytest

from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.models import GameState, ItemStatic, SourceProvenance
from LoLPerfmon.sim.models import RecipeGraph, validate_recipe_graph


def test_source_provenance_confidence():
    with pytest.raises(ValueError):
        SourceProvenance(source_name="x", confidence=2.0)


def test_game_state_slots():
    with pytest.raises(ValueError):
        GameState(0.0, FarmMode.LANE, 100.0, 0.0, 1, [None] * 5)


def test_recipe_graph_validate():
    items = {
        "a": ItemStatic("a", "A", 100.0, {}),
        "b": ItemStatic("b", "B", 200.0, {}),
    }
    g = RecipeGraph(
        parents_by_item={},
        children_by_item={},
        full_cost_by_item={"a": 100.0, "b": 200.0},
    )
    validate_recipe_graph(items, g)
