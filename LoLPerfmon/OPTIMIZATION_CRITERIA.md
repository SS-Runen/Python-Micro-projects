# Build optimization criteria (LoLPerfmon)

Normative rules for unconstrained farm / clear-speed search. Code paths that maximize something else must be labeled as **diagnostics**, not primary optimizers.

## Game scope

- **Classic Summoner’s Rift 5v5** only for default bundles and Data Dragon filters (see [`DATA_SOURCES.md`](DATA_SOURCES.md)). Lane vs jungle are **mutually exclusive** per run: a champion either farms **lane minion waves** (`FarmMode.LANE`) or **jungle camp cycles** (`FarmMode.JUNGLE`), not both in one simulation.

## Primary objective (farm income proxy)

| Use | Do not use as the optimization target |
|-----|----------------------------------------|
| **`SimResult.total_farm_gold`** over **`t_max`** (e.g. 3600s) in **`FarmMode.LANE`** or **`FarmMode.JUNGLE`** | **`final_gold`** / wallet balance (rewards underspending and sitting on gold) |
| Integrated income from the discrete wave or jungle route model in [`sim/simulator.py`](sim/simulator.py) | A single snapshot of **`effective_dps`** as the *only* global score |

[`default_build_optimizer_score`](sim/simulator.py) returns `total_farm_gold` by design.

**Passive gold** ([`passive_gold_in_interval`](sim/passive.py)) accrues between ticks in the same timeline as farm ticks. It does **not** depend on items in this model. Full forward simulations therefore capture part of the **opportunity cost** of delaying purchases: you may bank passive gold while farming slowly if you skip smaller combat purchases to save for an expensive item—`total_farm_gold` still reflects lost lane/jungle farm income over the horizon.

## What `total_farm_gold` means

- **Lane:** Sum of **discrete** per-wave gold ticks when lane farming: throughput from clear time vs wave interval, **not** a continuous last-hit model.
- **Jungle:** Sum of per-route gold ticks scaled by clear speed vs base cycle time.
- **Not** a claim of matching in-game CS/sec or client-accurate combat.

## Greedy and beam search

- **Global** maximization of `total_farm_gold` over all valid recipe-respecting purchase paths is **intractable** (huge branching factor × time horizon).
- **`greedy_farm_build`** ([`sim/greedy_farm_build.py`](sim/greedy_farm_build.py)): at each purchase opportunity, the affordable acquisition maximizing **Δeffective_dps / max(gold_paid, ε)** with deterministic tie-breaks. This is **myopic** and **not** globally optimal. Pass **`farm_mode`** (default **lane**) for lane vs jungle.
- **`beam_refined_farm_build`** / **`FarmBuildSearch`** ([`sim/farm_build_search.py`](sim/farm_build_search.py)): **bounded beam** over **purchase prefixes** of length up to **`beam_depth`**, keeping up to **`beam_width`** prefixes at each depth. Each leaf is a **full** `simulate` to **`t_max`** with **forced prefix** then **greedy** tail, scored by **`total_farm_gold`**. **`max_leaf_evals`** caps total full simulations.
- **`marginal_objective`** (at the **empty prefix** only): **`dps_per_gold`** (default) ranks next candidates by myopic ΔDPS/price; **`horizon_greedy_roi`** ranks them by nested full-sim **Δtotal_farm_gold** vs the pure-greedy baseline (extra cost; uses **`horizon_candidate_cap`** to limit candidates). Deeper beam steps (non-empty prefix) use **ΔDPS/gold** marginals for tractability.

## Recipe validity

- Purchases must succeed under [`acquire_goal`](sim/simulator.py) (Data Dragon–style craft, sticker buy, or component buy).
- **No duplicate finished items** where rules forbid: [`ItemDef.max_inventory_copies`](sim/models.py), [`blocked_purchase_ids`](sim/simulator.py), boots tag checks—see simulator and [`ddragon_fetch`](sim/ddragon_fetch.py).
- Do **not** optimize with [`best_item_order_exhaustive`](sim/optimizer.py) over a flat list that mixes a component and its parent as independent goals unless that is intentional and documented.

## Kit and item modeling limits

- **Lane/jungle clear rate** uses [`lane_clear_dps`](sim/clear.py) (alias **`effective_dps`**): **ability** damage from Data Dragon spell data when possible ([`spell_farm_model`](sim/spell_farm_model.py)), with kit fallbacks. **Auto-attack** clear uses `auto_attack_clear_weight × …`; mages often use **`auto_attack_clear_weight=0`**.
- Item **actives** and many passives are **not** modeled; stats come from Data Dragon flat stat lines on [`ItemDef`](sim/models.py).

## Parameters (defaults for scripts)

| Parameter | Typical value | Role |
|-----------|---------------|------|
| `t_max` | `3600` | Horizon (seconds) |
| `epsilon` | `1e-9` | Avoid division by zero in marginal score |
| `beam_depth` `D` | `1` | Prefix layers to branch (deeper = more search, slower) |
| `beam_width` `B` | `3` | Prefixes retained per depth |
| `max_leaf_evals` | `27` | Cap on full `simulate` calls in beam search |
| `farm_mode` | `LANE` | `LANE` = minion waves; `JUNGLE` = camp routes |
| `marginal_objective` | `dps_per_gold` | `horizon_greedy_roi` at empty prefix only (costly) |
| `eta_lane` | `1.0` | Lane throughput factor |

## Post-hoc checks

After a run, [`clear_upgrade_report`](sim/marginal_clear.py) reports whether a **full sticker** buy of another finished item would increase **effective_dps** with remaining gold and a free slot. It does **not** prove global farm optimality; it signals modeled one-step DPS saturation for that snapshot.
