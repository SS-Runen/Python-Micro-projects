# LoLPerfmon — lane farm simulation

Python simulation of discrete lane/jungle farm income and recipe-aware purchases (Data Dragon item/champion data when online). **Selling, swapping, and most item actives are not modeled.**

## Setup

From the **repository root** (parent of `LoLPerfmon/`):

```bash
python -m pytest LoLPerfmon/tests -q
```

Ensure `LoLPerfmon` is importable (run commands from repo root, or add the root to `PYTHONPATH`).

## Running simulations

### Greedy / beam “optimal” lane farm build (CLI)

Uses `beam_refined_farm_build`: at game start, compares the **greedy** run to up to **`beam_width`** different **first purchases**, then runs the same **greedy marginal** rule for the rest of the horizon. Default champions: Lux, Karthus, Quinn (offline: `generic_ap` only with a tiny item stub).

**Live Data Dragon** (full Summoner’s Rift catalog, needs network):

```bash
export LOLPERFMON_OFFLINE=0
python LoLPerfmon/scripts/run_greedy_farm_champions.py --t-max 3600 --beam-width 4 --timeout 60
```

**Offline** (no network, synthetic bundle):

```bash
export LOLPERFMON_OFFLINE=1
python LoLPerfmon/scripts/run_greedy_farm_champions.py
```

Useful flags: `--t-max` (seconds), `--beam-width`, `--max-leaf-evals`, `--timeout` (HTTP timeout for Data Dragon when online).

### Programmatic API

- `LoLPerfmon.sim.simulator.simulate` — lane or jungle ticks with optional `lane_purchase_hook` or fixed `PurchasePolicy(buy_order=...)`.
- `LoLPerfmon.sim.greedy_farm_build.greedy_farm_build` / `beam_refined_farm_build` — unconstrained farm build search.
- Notebook `LoLPerfmon/waveclear_item_optimizer.ipynb` — examples and validation entrypoints.

### Checks without pytest

```bash
python -c "from LoLPerfmon.validation_checks import format_report, run_validation, validation_summary; r=run_validation(data_dir=None, offline=True); print(format_report(r, style='text')); print(validation_summary(r))"
```

## Interpreting results

### What to optimize (primary score)

For build search, the intended objective is **`SimResult.total_farm_gold`** over **`t_max`** in **`FarmMode.LANE`**: integrated gold from **discrete per-wave** clears when the model says you full-clear, **not** residual **`final_gold`** (wallet balance can reward not spending). See **`OPTIMIZATION_CRITERIA.md`**.

### What the printed “buy order” is

It is the **sequence of successful `acquire_goal` purchases** over the run (components, crafts, full buys). Repeated names usually mean **components were crafted away** before the same item id is bought again—check recipe consumption, not “two copies in inventory.”

### Greedy / beam are not globally optimal

`beam_refined_farm_build` uses **beam depth 1** only: it branches on the **first** purchase only, then follows a **myopic** greedy rule (`Δeffective_dps / gold`). That is **not** an exhaustive search over all legal build paths; different `beam_width` may or may not change the winner.

### `clear_upgrade_report` (CLI tail line)

After a run, the script reports whether **`clear_upgrade_report`** finds an affordable **full sticker** buy that would increase **modeled `effective_dps`**. **`saturated: True`** means that snapshot has no such step; it does **not** prove global farm optimality.

### Data and rules

- Item/champion sourcing and filters: **`DATA_SOURCES.md`**.
- Purchase validity (recipes, `max_inventory_copies`, boots, blocked rebuys): implemented in **`sim/simulator.py`** and **`sim/ddragon_fetch.py`**.
