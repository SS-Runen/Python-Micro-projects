# LoLPerfmon

Farming speed model, deterministic farm simulator, and beam-search item purchase paths.

## Layout

- `sim/` — config, models, economy, combat throughput, simulator, metrics, search
- `data/` — canonical JSON (champions, items, minions, monsters), manifest
- `ingest/` — Data Dragon fetch, normalization, reconciliation, updater
- `scripts/` — `run_optimize_farm_build.py`, `run_optimize_batch.py`, `sync_game_data.py`, `audit_data_discrepancies.py`
- `tests/`

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest LoLPerfmon/tests -q
.venv/bin/python LoLPerfmon/scripts/run_optimize_farm_build.py --champion lux --mode lane
```

Data sync (network): fetches Data Dragon, stores raw under `data/raw/ddragon/<patch>/`. Use `--write-canonical` to write all normalized items (large).

```bash
.venv/bin/python LoLPerfmon/scripts/sync_game_data.py --dry-run
.venv/bin/python LoLPerfmon/scripts/audit_data_discrepancies.py
```

## Notes

- Wiki parsing is stubbed; reconcile pipeline supports Data Dragon vs on-disk canonical items.
- See [Data Dragon](https://riot-api-libraries.readthedocs.io/en/latest/ddragon.html) for upstream semantics.
