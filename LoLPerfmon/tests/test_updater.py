from pathlib import Path

from LoLPerfmon.ingest.updater import write_data_bundle


def test_write_bundle_dry_run(tmp_path: Path):
    rep = write_data_bundle(tmp_path, {"x": {"item_id": "x", "name": "X", "cost": 1.0}}, patch="t", dry_run=True)
    assert rep.dry_run
    assert len(rep.wrote_paths) == 0
