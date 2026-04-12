"""Champion id resolution from Data Dragon ``champion.json`` shape (no network)."""

from __future__ import annotations

import pytest

from LoLPerfmon.sim.ddragon_fetch import ChampionDDragonIndex, champion_index_from_list_payload

MINIMAL_CHAMPION_LIST = {
    "type": "champion",
    "format": "standAloneComplex",
    "version": "99.99.1",
    "data": {
        "Lux": {"id": "Lux", "key": "99", "name": "Lux"},
        "MonkeyKing": {"id": "MonkeyKing", "key": "62", "name": "Wukong"},
        "Kaisa": {"id": "Kaisa", "key": "145", "name": "Kai'Sa"},
        "Nunu": {"id": "Nunu", "key": "20", "name": "Nunu & Willump"},
    },
}


@pytest.fixture
def idx() -> ChampionDDragonIndex:
    return champion_index_from_list_payload(MINIMAL_CHAMPION_LIST)


def test_resolves_ddragon_id_and_display_name(idx: ChampionDDragonIndex) -> None:
    assert idx.resolve("lux") == "Lux"
    assert idx.resolve("Lux") == "Lux"
    assert idx.resolve("monkeyking") == "MonkeyKing"
    assert idx.resolve("MonkeyKing") == "MonkeyKing"
    assert idx.resolve("wukong") == "MonkeyKing"
    assert idx.resolve("Wukong") == "MonkeyKing"


def test_resolves_apostrophe_and_compact_names(idx: ChampionDDragonIndex) -> None:
    assert idx.resolve("kaisa") == "Kaisa"
    assert idx.resolve("Kai'Sa") == "Kaisa"


def test_resolves_ampersand_display_name(idx: ChampionDDragonIndex) -> None:
    assert idx.resolve("nunu & willump") == "Nunu"
    assert idx.resolve("nunuwillump") == "Nunu"


def test_unknown_returns_none(idx: ChampionDDragonIndex) -> None:
    assert idx.resolve("notachampion") is None
    assert idx.resolve("") is None
