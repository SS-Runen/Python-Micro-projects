from LoLPerfmon.data.loaders import data_root_default, load_bundle
from LoLPerfmon.sim.config import FarmMode
from LoLPerfmon.sim.search import BeamSearchConfig, beam_search_farm_build


def test_beam_search_runs():
    root = data_root_default()
    ch, items, units, _ = load_bundle(root)
    cfg = BeamSearchConfig(beam_width=2, max_depth=2, max_leaf_evals=32, t_max=300.0)
    order, score, res = beam_search_farm_build(
        ch["lux"],
        FarmMode.LANE,
        items,
        tuple(sorted(items.keys())),
        lane_minion=units["lane_melee"],
        jungle_monster=None,
        cfg=cfg,
        leaf_score="total_farm_gold",
    )
    assert score == res.total_farm_gold
    assert isinstance(order, tuple)
