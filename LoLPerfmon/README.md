# LoLPerfmon

Farming speed model, deterministic farm simulator, and beam-search item purchase paths.

## Layout

- `sim/` — config, models, economy, combat throughput, simulator, sim logging, search
- `data/` — canonical JSON (champions, items, minions, monsters), manifest
- `ingest/` — Data Dragon fetch, normalization, reconciliation, updater
- `scripts/` — CLIs below
- `tests/` — `pytest` suite (see [Tests](#tests))

## Setup

From the **repository root** (`Python-Micro-projects`), create a virtual environment and install the test runner:

```bash
python3 -m venv .venv
.venv/bin/pip install pytest
```

All examples below assume you run commands from the repository root and use `.venv/bin/python`. If you prefer, activate the venv (`source .venv/bin/activate`) and use `python` instead.

Scripts add the repo root to `sys.path` so `LoLPerfmon` imports resolve when run as files.

---

## Scripts

### `scripts/run_sim.py`

Standard entry point: **beam search** over item buy orders from **00:00** game time. Use `--champion` or `--champions`, and `--role laner` or `--role jungler` (not `lane`/`jungle`). Loads bundled data from `LoLPerfmon/data/`.

| Option | Description |
|--------|-------------|
| `--champion` / `--champions` | One champion id, or several for a batch summary. |
| `--role` | Required. `laner` or `jungler`. |
| `--t-max` | Simulation horizon in seconds (default `600`). |
| `--starter-item` / `--no-starter` | Optional starting item; defaults by role when omitted. |
| `--beam-width`, `--max-depth`, `--max-leaf-evals`, `--leaf-score` | Beam search tuning (same idea as before). |
| `--log-interval SEC` | After search, **replay** the best buy order once and log simulator state every `SEC` game seconds to stderr (e.g. `10` for troubleshooting accuracy). Single `--champion` runs only; `0` disables (default). |

**Examples:**

```bash
.venv/bin/python LoLPerfmon/scripts/run_sim.py --champion lux --role laner
.venv/bin/python LoLPerfmon/scripts/run_sim.py --champion karthus --role jungler --t-max 900 --leaf-score total_clear_units
.venv/bin/python LoLPerfmon/scripts/run_sim.py --champions lux karthus --role laner
.venv/bin/python LoLPerfmon/scripts/run_sim.py --champion lux --role laner --log-interval 10 --no-starter --t-max 120
```

---

### `scripts/sync_game_data.py`

Fetches **Data Dragon** `item.json` for the latest patch (or `--patch`), saves a **raw** copy under `LoLPerfmon/data/raw/ddragon/<patch>/`, normalizes items, and compares to on-disk `data/items/*.json`.

| Option | Description |
|--------|-------------|
| `--patch` | Data Dragon version string (default: latest from Riot `versions.json`). |
| `--dry-run` | Do not write canonical `data/items` or manifest (still writes raw snapshot unless you rely on dry semantics below). |
| `--write-canonical` | Write **all** normalized items into `data/items` and update `data/manifest/data_manifest.json` (**large**; overwrites many files). |
| `--out-diff` | Optional path to write a JSON file of discrepancy records. |
| `--data-root` | Optional override; default is `LoLPerfmon/data`. |

**Default behavior:** without `--write-canonical`, canonical item files are **not** updated (`dry_run` is effectively true for `write_data_bundle`). Raw `item.json` is still written under `data/raw/ddragon/<patch>/`. Use `--write-canonical` only when you intend to refresh the full item catalog.

**Examples:**

```bash
# Fetch latest patch, save raw snapshot, print stats (no bulk canonical write)
.venv/bin/python LoLPerfmon/scripts/sync_game_data.py

# Same, plus save discrepancy report
.venv/bin/python LoLPerfmon/scripts/sync_game_data.py --out-diff LoLPerfmon/data/diffs/last_sync.json

# Full canonical refresh (many files)
.venv/bin/python LoLPerfmon/scripts/sync_game_data.py --write-canonical
```

**Requires network** access to `ddragon.leagueoflegends.com`.

---

### `scripts/audit_data_discrepancies.py`

Dry-run only: compares **local** `data/items` to Data Dragon normalized items and prints counts. Optionally writes a full discrepancy JSON.

| Option | Description |
|--------|-------------|
| `--patch` | Data Dragon version (default: latest). |
| `--data-root` | Optional; default `LoLPerfmon/data`. |
| `--out` | Optional path to write discrepancy JSON. |

**Example:**

```bash
.venv/bin/python LoLPerfmon/scripts/audit_data_discrepancies.py
.venv/bin/python LoLPerfmon/scripts/audit_data_discrepancies.py --out LoLPerfmon/data/diffs/audit.json
```

**Requires network.**

---

## Tests

```bash
.venv/bin/python -m pytest LoLPerfmon/tests -q
```

---

## Notes

- Wiki parsing in `ingest/wiki_parser.py` is minimal; reconciliation is centered on Data Dragon vs bundled canonical items.
- See [Data Dragon](https://riot-api-libraries.readthedocs.io/en/latest/ddragon.html) for upstream semantics.
