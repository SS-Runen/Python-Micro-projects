"""Data Dragon availability audit — oracles in ``ddragon_fixture_checks``."""

from __future__ import annotations

from LoLPerfmon.sim.ddragon_availability import ITEM_STATS_KEYS_MAPPED, audit_champion_raw
from LoLPerfmon.sim.ddragon_fixture_checks import verify_frozen_sample_payloads
from LoLPerfmon.sim.ddragon_sample_payloads import LUX_CHAMPION_EXCERPT


def test_frozen_sample_payloads_contract() -> None:
    """Shared with ``python -m LoLPerfmon.validation_checks`` — no duplicate tautologies."""
    verify_frozen_sample_payloads()


def test_unmapped_stat_requires_unknown_key() -> None:
    """Blasting Wand excerpt is only flagged if the extra key is outside the mapped stat set."""
    assert "UnknownRiotStat" not in ITEM_STATS_KEYS_MAPPED


def test_audit_champion_flags_numeric_stats_not_in_profile() -> None:
    """``movespeed`` is real DD data we do not model; warning must mention the key."""
    w = audit_champion_raw("lux", LUX_CHAMPION_EXCERPT)
    assert any("movespeed" in x for x in w)
