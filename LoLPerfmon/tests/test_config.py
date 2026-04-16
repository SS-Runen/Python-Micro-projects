from LoLPerfmon.sim.config import PASSIVE_GOLD_AT_5MIN, PASSIVE_GOLD_PER_SEC
from LoLPerfmon.sim.economy import passive_gold_over_interval
from LoLPerfmon.sim.simulator import verify_passive_gold_at_5min


def test_passive_gold_per_second():
    assert abs(PASSIVE_GOLD_PER_SEC - 1.6) < 1e-9


def test_passive_gold_5min():
    assert abs(passive_gold_over_interval(300.0) - PASSIVE_GOLD_AT_5MIN) < 0.01
    assert verify_passive_gold_at_5min()
