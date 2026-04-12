"""Network checks: Data Dragon recipe closure and mythic post-order."""

from __future__ import annotations

import os

import pytest

from LoLPerfmon.sim.bundle_factory import build_bundle_from_ddragon, latest_version
from LoLPerfmon.sim.build_path_optimizer import acquisition_postorder_for_item, optimal_interleaved_build
from LoLPerfmon.sim.config import FarmMode


@pytest.mark.integration
def test_ludens_bundle_has_recipe_closure_and_optimal_runs() -> None:
    if os.environ.get("LOLPERFMON_OFFLINE", "1").lower() in ("1", "true", "yes"):
        pytest.skip("set LOLPERFMON_OFFLINE=0 for Data Dragon")
    ver = latest_version(timeout=25.0)
    if not ver:
        pytest.skip("could not fetch versions.json")
    data = build_bundle_from_ddragon(ver, timeout=30.0)
    assert data is not None
    ludens = "6655"
    if ludens not in data.items:
        pytest.skip("Luden's id not in filtered bundle for this patch")
    assert data.items[ludens].from_ids, "expected mythic to list components"
    seq = acquisition_postorder_for_item(ludens, data.items)
    assert seq[-1] == ludens
    order, val, res = optimal_interleaved_build(
        data,
        "lux",
        FarmMode.LANE,
        (ludens,),
        t_max=2400.0,
        max_interleave_steps=20,
    )
    assert order == seq
    assert ludens in res.final_inventory
    assert val == res.total_farm_gold
