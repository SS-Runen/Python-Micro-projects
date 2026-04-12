# Build optimization criteria (LoLPerfmon)

Normative rules for unconstrained farm / clear-speed search. Code paths that maximize something else must be labeled as **diagnostics**, not primary optimizers.

## Primary objective (lane farm / clear proxy)

| Use | Do not use as the optimization target |
|-----|----------------------------------------|
| **`SimResult.total_farm_gold`** over **`t_max`** (e.g. 3600s) in **`FarmMode.LANE`** | **`final_gold`** / wallet balance (rewards underspending and sitting on gold) |
| Integrated income from the discrete wave model in [`sim/simulator.py`](sim/simulator.py) | A single snapshot of **`effective_dps`** as the *only* score (DPS is a **local heuristic** inside greedy search and for tie-breaks) |

[`default_build_optimizer_score`](sim/simulator.py) returns `total_farm_gold` by design.

## What `total_farm_gold` means

- Sum of **discrete** per-wave gold ticks when lane farming: throughput from clear time vs wave interval, **not** a continuous last-hit model.
- **Not** a claim of matching in-game CS/sec or client-accurate combat.

## Greedy and beam search

- **Global** maximization of `total_farm_gold` over all valid recipe-respecting purchase paths is **intractable** (huge branching factor × time horizon).
- **`greedy_farm_build`** (see [`sim/greedy_farm_build.py`](sim/greedy_farm_build.py)) picks, at each purchase opportunity, the affordable acquisition maximizing **Δeffective_dps / max(gold_paid, ε)** with deterministic tie-breaks. This is **myopic** and **not** globally optimal.
- **`beam_refined_farm_build`** (depth **1** in the implementation): compares the pure greedy run to **top-B** first purchases from ranked marginals at **t=0**, each followed by the same greedy rule. **`max_leaf_evals`** caps total full simulations. Deeper beam (branching at later decisions with mid-game state) is not implemented; **`beam_depth` > 1** is clamped to **1**.

## Recipe validity

- Purchases must succeed under [`acquire_goal`](sim/simulator.py) (Data Dragon–style craft, sticker buy, or component buy).
- Do **not** optimize with [`best_item_order_exhaustive`](sim/optimizer.py) over a flat list that mixes a component and its parent as independent goals unless that is intentional and documented.

## Kit and item modeling limits

- **Lane/jungle clear rate** uses [`lane_clear_dps`](sim/clear.py) (alias **`effective_dps`**): **ability** damage is derived from Data Dragon spell **`effect`** base values and **`vars`** coeff lists when possible ([`spell_farm_model`](sim/spell_farm_model.py)), with **kit fallbacks** for scalings missing from JSON. **Auto-attack** clear is `auto_attack_clear_weight × as_weight × attack_speed × attack_damage`; mages use **`auto_attack_clear_weight=0`** so AD/AS items do not fake spell waveclear (see [`KitParams`](sim/models.py)).
- If no spell lines parse, the sim falls back to linear [`KitParams`](sim/models.py) weights (legacy).
- Item **actives** and many passives are **not** modeled; stats come from Data Dragon flat stat lines on [`ItemDef`](sim/models.py).
- Quinn remains AD-skewed via kit + spell `vars` when present.

## Parameters (defaults for scripts)

| Parameter | Typical value | Role |
|-----------|---------------|------|
| `t_max` | `3600` | Horizon (seconds) |
| `epsilon` | `1e-9` | Avoid division by zero in marginal score |
| `beam_depth` `D` | `3` | Branching depth for beam |
| `beam_width` `B` | `3` | Alternatives per depth |
| `eta_lane` | `1.0` | Lane throughput factor |

## Post-hoc checks

After a run, [`clear_upgrade_report`](sim/marginal_clear.py) reports whether a **full sticker** buy of another finished item would increase **effective_dps** with remaining gold and a free slot. It does **not** prove global farm optimality; it signals modeled one-step DPS saturation for that snapshot.
