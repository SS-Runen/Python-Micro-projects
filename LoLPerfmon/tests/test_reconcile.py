from LoLPerfmon.ingest.reconcile import compute_discrepancies


def test_discrepancy_cost_drift():
    a = {"1": {"name": "X", "cost": 100.0}}
    b = {"1": {"name": "X", "cost": 200.0}}
    d = compute_discrepancies(a, b, source_name="t")
    assert any(x.field_path == "cost" for x in d)
