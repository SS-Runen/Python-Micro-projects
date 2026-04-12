"""Spell parsing and DPS hook — table-driven and minimal-shape isolation."""

from __future__ import annotations

import math

import pytest

from LoLPerfmon.sim.ddragon_spell_parse import (
    base_ability_dps_hint_from_mean_cooldown,
    kit_params_from_spells,
    parse_champion_spells,
    parse_spell_entry,
)
from LoLPerfmon.sim.ddragon_sample_payloads import LUX_CHAMPION_EXCERPT


@pytest.mark.parametrize(
    ("mean_cd", "expected"),
    [
        (0.2, 48.0),
        (10.0, 11.0),
        (100.0, 6.0),
    ],
)
def test_base_ability_dps_hint_table(mean_cd: float, expected: float) -> None:
    """Bounded hook is tested directly; kit integration uses the same function."""
    got = base_ability_dps_hint_from_mean_cooldown(mean_cd)
    assert math.isclose(got, expected), f"mean_cd={mean_cd}: got {got}, want {expected}"


def test_parse_vars_minimal_dict_isolation() -> None:
    """Not from a CDN excerpt — isolates ``{key, coeff}`` handling only."""
    raw = {
        "id": "TestQ",
        "name": "Test",
        "cooldown": [5.0],
        "cost": [],
        "maxrank": 1,
        "costType": "",
        "vars": [{"key": "ratio", "coeff": [0.1, 0.2, 0.3]}],
        "effect": [],
    }
    sp = parse_spell_entry("q", raw)
    assert len(sp.vars) == 1
    assert sp.vars[0].key == "ratio"
    assert sp.vars[0].coeffs == (0.1, 0.2, 0.3)


def test_lux_excerpt_real_data_has_empty_vars() -> None:
    """Riot 14.23.1 Lux Q ships ``vars: []`` — parser must not invent coefficients."""
    data = parse_champion_spells("Lux", LUX_CHAMPION_EXCERPT)
    assert len(data.spells) == 1
    assert data.spells[0].vars == ()
