# LoLPerfmon — lane / jungle farm simulation

Python simulation of discrete **lane** or **jungle** farm income and recipe-aware purchases (Data Dragon when online). Scope: **Classic Summoner’s Rift 5v5**. **Selling, swapping, and most item actives are not modeled.**

## Setup

From the **repository root** (parent of `LoLPerfmon/`):

```bash
python -m pytest LoLPerfmon/tests -q
```

Ensure `LoLPerfmon` is importable (run commands from repo root, or add the root to `PYTHONPATH`).

## Running simulations

### Greedy / beam farm build (CLI)

Uses **`beam_refined_farm_build`**: runs a **pure greedy** baseline, then **beam search** over **purchase prefixes** up to **`beam_depth`** with width **`beam_width`**, each leaf scored by full-horizon **`total_farm_gold`**. Default champions: Lux, Karthus, Quinn (offline: `generic_ap` only).

**Live Data Dragon** (full SR catalog, needs network):

```bash
export LOLPERFMON_OFFLINE=0
python LoLPerfmon/scripts/run_greedy_farm_champions.py --t-max 3600 --beam-width 3 --beam-depth 2 --farm-mode lane --timeout 60
```

**Offline**:

```bash
export LOLPERFMON_OFFLINE=1
python LoLPerfmon/scripts/run_greedy_farm_champions.py
```

Useful flags:

| Flag | Meaning |
|------|---------|
| `--t-max` | Horizon (seconds) |
| `--beam-width` | Prefixes kept per beam layer |
| `--beam-depth` | How many purchase layers to branch |
| `--max-leaf-evals` | Cap on full `simulate` calls |
| `--farm-mode` | `lane` (default) or `jungle` — mutually exclusive income |
| `--marginal-objective` | `dps_per_gold` (default) or `horizon_greedy_roi` (nested sims at empty prefix; costly) |
| `--horizon-candidate-cap` | Max candidates when ranking with `horizon_greedy_roi` |
| `--timeout` | HTTP timeout for Data Dragon when online |

### Programmatic API

- `LoLPerfmon.sim.simulator.simulate` — lane or jungle ticks with optional **`purchase_hook`** or fixed `PurchasePolicy(buy_order=...)`.
- `LoLPerfmon.sim.greedy_farm_build.greedy_farm_build` / `beam_refined_farm_build` — greedy and beam search; pass **`farm_mode`**.
- `LoLPerfmon.sim.farm_build_search.FarmBuildSearch` — configurable beam search class.
- Notebook `LoLPerfmon/waveclear_item_optimizer.ipynb` — examples and validation entrypoints.

### Checks without pytest

```bash
python -c "from LoLPerfmon.validation_checks import format_report, run_validation, validation_summary; r=run_validation(data_dir=None, offline=True); print(format_report(r, style='text')); print(validation_summary(r))"
```

## Interpreting results

### What to optimize (primary score)

The intended objective is **`SimResult.total_farm_gold`** over **`t_max`** (lane or jungle), **not** residual **`final_gold`**. Passive gold accrues on the same timeline; see **`OPTIMIZATION_CRITERIA.md`**.

### What the printed “buy order” is

The **sequence of successful `acquire_goal` purchases** (components, crafts, full buys). Repeated names often mean **components were crafted away** before the same id is bought again.

### Greedy / beam are not globally optimal

Beam search is **bounded** (`beam_depth`, `beam_width`, `max_leaf_evals`). It is **not** exhaustive over all purchase orders.

### `clear_upgrade_report` (CLI tail line)

Reports whether a hypothetical **full sticker** buy would increase **modeled `effective_dps`** at the end snapshot; it does **not** prove global farm optimality.

### Data and rules

- Source hierarchy and SR 5v5: **`DATA_SOURCES.md`**.
- Purchase validity: **`sim/simulator.py`**, **`sim/ddragon_fetch.py`**.
