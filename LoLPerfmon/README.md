# LoLPerfmon

Farming speed model, deterministic farm simulator, and beam-search item purchase paths.

## Layout

- `sim/` — config, models, economy, combat throughput, simulator, metrics, search
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

### `scripts/run_optimize_farm_build.py`

Beam search over item buy orders for **one** champion. Loads bundled data from `LoLPerfmon/data/`.

| Option | Description |
|--------|-------------|
| `--champion` | Required. Champion id matching `data/champions/<id>.json` (e.g. `lux`, `karthus`). |
| `--mode` | Required. `lane` or `jungle`. |
| `--t-max` | Simulation horizon in seconds (default `600`). |
| `--beam-width` | Beam width (default `4`). |
| `--max-depth` | Max purchases in the sequence (default `4`). |
| `--max-leaf-evals` | Cap on simulator evaluations (default `128`). |
| `--leaf-score` | `total_farm_gold` or `total_clear_units` (default `total_farm_gold`). |

**Examples:**

```bash
.venv/bin/python LoLPerfmon/scripts/run_optimize_farm_build.py --champion lux --mode lane
.venv/bin/python LoLPerfmon/scripts/run_optimize_farm_build.py --champion karthus --mode jungle --t-max 900 --leaf-score total_clear_units
```

---

### `scripts/run_optimize_batch.py`

Same optimizer as above, but runs **several** champions in one invocation. Uses fixed internal beam settings (`beam_width=4`, `max_depth=3`, `max_leaf_evals=64`).

| Option | Description |
|--------|-------------|
| `--champions` | Required. One or more champion ids. Unknown ids are skipped with a message. |
| `--mode` | Required. `lane` or `jungle`. |
| `--t-max` | Simulation horizon in seconds (default `600`). |

**Example:**

```bash
.venv/bin/python LoLPerfmon/scripts/run_optimize_batch.py --champions lux karthus --mode lane
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
