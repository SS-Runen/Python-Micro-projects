# Build optimization criteria (LoLPerfmon)

Normative rules for unconstrained farm / clear-speed search. Code paths that maximize something else must be labeled as **diagnostics**, not primary optimizers.

## Game scope

- **Classic Summoner’s Rift 5v5** only for default bundles and Data Dragon filters (see [`DATA_SOURCES.md`](DATA_SOURCES.md)). Lane vs jungle are **mutually exclusive** per run: a champion either farms **lane minion waves** (`FarmMode.LANE`) or **jungle camp cycles** (`FarmMode.JUNGLE`), not both in one simulation.

### Jungle companion (mandatory) and sell timing

- **No half-XP without a jungle item** is modeled: the abstract route XP/gold formulas in [`sim/simulator.py`](sim/simulator.py) do not apply a “laner tax” or dual-path XP. Junglers are always assumed to clear with a companion for the purpose of this farm model.
- **`FarmMode.JUNGLE` always starts with one jungle companion** identified by Data Dragon’s **`Jungle` tag** (e.g. Gustwalker Hatchling, Mosstomper Seedling, Scorchclaw Pup on live patches). It is **bought from starting gold** at `t=0` (same as [`acquire_goal`](sim/simulator.py)); [`resolve_jungle_starter_item_id`](sim/jungle_items.py) picks the lexicographically first companion in the bundle if you do not pass `jungle_starter_item_id` to [`simulate`](sim/simulator.py) / [`beam_refined_farm_build`](sim/greedy_farm_build.py).
- **Companion treat evolution** (e.g. **15** and **35** large-monster treats on Classic SR for pet evolutions) is documented on the wiki ([Jungling § Jungle items](https://wiki.leagueoflegends.com/en-us/Jungling)); this simulator **does not** track treats or Smite tier names—only **flat stats** on [`ItemDef`](sim/models.py) affect [`effective_dps`](sim/clear.py) and jungle cycle scaling.
- **Selling the companion** is optional: [`simulate`](sim/simulator.py) accepts `jungle_sell_at_seconds` and `jungle_sell_only_after_level_18`. On the first jungle cycle at or after `jungle_sell_at_seconds`, if the companion is still owned (and level ≥ 18 when the flag is set), it is sold once for **`JUNGLE_COMPANION_SELL_REFUND_FRACTION` × `total_cost`** (same **50%** as [`STANDARD_SHOP_SELL_REFUND_FRACTION`](sim/sell_economy.py); see [`jungle_items.py`](sim/jungle_items.py)).
- **Optimal sell timing search** (maximize [`default_build_optimizer_score`](sim/simulator.py), i.e. `total_farm_gold`): [`optimal_jungle_sell_timing`](sim/jungle_sell_timing.py) scans **never sell** and **sell at each jungle cycle boundary** up to `t_max` with the same greedy purchase hook, and returns the best-scoring `jungle_sell_at_seconds` (or `None` for never sell).

## Modeling assumptions (deterministic)

The farm simulator is **fully deterministic** (no last-hit RNG, crit variance, or Monte Carlo). Selling credits **50%** of `ItemDef.total_cost` ([`shop_sell_refund_gold`](sim/sell_economy.py)), not necessarily Data Dragon `gold.sell` per item.

| ID | Assumption | Implication |
|----|------------|-------------|
| A1 | Lane income from **wave throughput** (`throughput_ratio` × wave value), not per-minion rolls | “Perfect” fractional clear from DPS vs wave HP budget |
| A2 | No combat RNG in [`effective_dps`](sim/clear.py) | No variance bands |
| A3 | Fixed wave clock from `GameRules` | No lane-freeze lever |
| A4 | Lane XP = minion XP tables × same throughput as gold | No champion-kill XP |
| A5 | Jungle abstract route; pet treat counts not tracked | Wiki thresholds documentation-only |
| A6 | Instant shop purchases | No latency |
| A7 | Flat stats on items; most actives/passives omitted | Client-strong items may be weak here |
| A8 | State advances on **discrete events** (per wave / per jungle cycle), not a universal ODE `dt` | See **Temporal resolution** below |
| A9 | Sell refund **50%** of `total_cost` | Unified with [`sell_item_once`](sim/simulator.py) |

Optional: **`use_level_weighted_marginal`** in [`make_stepwise_farm_hook`](sim/greedy_farm_build.py) (alias `make_greedy_hook`) blends farm-tick marginal score with raw ΔDPS/gold by champion level (early = more weight on capped farm derivative).

## Temporal resolution

- **Macro clock:** Lane steps once per wave arrival (`first_wave_spawn + k × wave_interval`); jungle steps once per `jungle_base_cycle_seconds`. Farm and XP apply on those boundaries; there is no user-tuned global `Δt` for the forward loop.
- **Passive gold:** [`passive_gold_in_interval`](sim/passive.py) over real time between event boundaries.
- **Marginal derivative:** [`marginal_farm_tick.py`](sim/marginal_farm_tick.py) uses SciPy `approx_fprime` on DPS → tick gold; step size scales with `max(1, |dps|)`. Stability can be checked by comparing derivatives at nearby DPS (see tests).

## Primary objective (farm income proxy)

| Use | Do not use as the optimization target |
|-----|----------------------------------------|
| **`SimResult.total_farm_gold`** over **`t_max`** (e.g. 3600s) in **`FarmMode.LANE`** or **`FarmMode.JUNGLE`** | **`final_gold`** / wallet balance (rewards underspending and sitting on gold) |
| Integrated income from the discrete wave or jungle route model in [`sim/simulator.py`](sim/simulator.py) | A single snapshot of **`effective_dps`** as the *only* global score |

[`default_build_optimizer_score`](sim/simulator.py) returns `total_farm_gold` by design.

## Clear volume (minions / monsters)

When the goal is **maximum modeled clears** (uniform minion count per wave, or abstract monsters per jungle route), not gold-weighted lane income:

- **Lane:** [`SimResult.total_lane_minions_cleared`](sim/simulator.py) sums `throughput_ratio × eta_lane × (melee + caster + siege)` each wave. This **differs** from maximizing `total_farm_gold` when per-minion gold values differ by type.
- **Jungle:** [`SimResult.total_jungle_monsters_cleared`](sim/simulator.py) sums `eff × GameRules.jungle_monsters_per_route` each cycle (default `monsters_per_route` is **1.0** if omitted in bundle JSON).
- **Score helper:** [`default_clear_count_score`](sim/simulator.py)(`res`, `farm_mode`) selects the appropriate field.
- **Search:** [`FarmBuildSearch`](sim/farm_build_search.py) / [`beam_refined_farm_build`](sim/greedy_farm_build.py) support `leaf_score='total_clear_units'`; stepwise marginals use **clear-count tick** derivatives when that leaf is selected (see [`marginal_clear_units_per_tick_derivative`](sim/marginal_farm_tick.py)).

**Passive gold** ([`passive_gold_in_interval`](sim/passive.py)) accrues between ticks in the same timeline as farm ticks. It does **not** depend on items in this model. Full forward simulations therefore capture part of the **opportunity cost** of delaying purchases: you may bank passive gold while farming slowly if you skip smaller combat purchases to save for an expensive item—`total_farm_gold` still reflects lost lane/jungle farm income over the horizon.

### Myopic marginal equivalence (`clear_count` vs `farm_gold`)

Under the capped throughput model ([`throughput_ratio`](sim/clear.py), [`marginal_farm_tick.py`](sim/marginal_farm_tick.py)):

- **Lane:** For a fixed wave snapshot, `gold_tick = wave_gold_if_full_clear × thr(DPS)` and `minions_tick = N × thr(DPS)` with the **same** `thr`. The greedy marginal uses `(d tick / d dps) × Δdps / paid`; `d(gold_tick)/d(dps)` and `d(minions_tick)/d(dps)` differ only by a **constant** (`gold_full` vs `N`), so **relative ordering of candidate items is unchanged** when switching `marginal_tick_objective` between `farm_gold` and `clear_count` at that snapshot (same `marginal_income_cap` / same wave inputs).
- **Jungle:** Route gold and abstract monsters per cycle are both **linear in the same `eff(DPS)`** term; derivatives w.r.t. DPS differ by a constant per cycle. Same **marginal ordering** as farm gold.

**Implication:** Greedy inner steps that rank by capped tick derivatives do **not** separate “gold farming” from “clear volume” myopia—they are **order-equivalent** under the current linear-in-throughput structure. Accumulated totals (`total_lane_minions_cleared`, `total_farm_gold`) still differ across full runs when per-minion gold weights differ, but **per-step greedy ranking** matches farm gold. Beam search with `leaf_score='total_clear_units'` compares **full simulations** at leaves; the **first** purchase at the empty prefix still follows whatever **empty-prefix** marginal ranking you configure (`dps_per_gold` vs `horizon_greedy_roi` in [`farm_build_search.py`](sim/farm_build_search.py)). The export script [`scripts/export_gameplay_build_orders.py`](scripts/export_gameplay_build_orders.py) defaults `marginal_objective=horizon_greedy_roi` when `leaf_score=total_clear_units` so the opening buy is ranked by nested full-sim Δprimary, not only myopic tick derivatives.

**Throughput saturation:** When `throughput_ratio` (lane) or effective route scaling (jungle) is already at the cap, `d(thr)/d(dps)` (or `d(eff)/d(dps)`) is ~0, so marginals that only add DPS past saturation score poorly—**both** farm and clear objectives agree on skipping those purchases at the **next** tick.

### Unit normalization (gold, minions, monsters)

Gold, lane minion counts, and jungle monster counts are **different dimensions**. Do not add them into one scalar **without** explicit scaling (e.g. normalize each term to a comparable range, or express clears per gold when the denominator is gold).

1. **Single-objective runs:** Optimizing **only** clears should use `default_clear_count_score` / `total_lane_minions_cleared` / `total_jungle_monsters_cleared` alone—do not add raw `total_farm_gold` into the same scalar without normalization.
2. **Horizon ROI (`horizon_greedy_roi`):** Ranks candidates by `Δprimary / gold_paid`. For `leaf_score=total_farm_gold`, `Δprimary` is gold; for `leaf_score=total_clear_units`, `Δprimary` is **Δclears**—the ratio is **clears per gold** on that step (valid; **not** comparable numerically across different `leaf_score` choices without converting to a common unit).
3. **Future multi-objective scores:** Any blend `w1 * gold + w2 * minions` needs explicit weights or per-run normalization; document constants in tests or docs.

Myopic equivalence above is **not** fixed by “normalizing units” in the marginal score—it prevents **illegal** mixing of unrelated totals, not the algebraic proportionality of lane/jungle tick models.

### Catalog policy (why “carry” champions can show support mythics)

Default ranked SR bundles do **not** filter by role line. Items with the Data Dragon **`Support`** tag (often cheap full endpoints with AP) compete with “Damage” items unless you **exclude tags** at load or export time ([`sim/item_tag_filters.py`](sim/item_tag_filters.py), [`scripts/export_gameplay_build_orders.py`](scripts/export_gameplay_build_orders.py)).

### Wave-clear catalog heuristics (explore full SR, then search)

Blind greedy or beam search over the **entire** ranked-SR item dict is a poor match for “high-stat finished carry” narratives: myopic marginals favor cheap ΔDPS/gold steps, and throughput saturation zeros out farm/clear derivatives. The intended **primary** workflow is still **catalog-driven** (no user-supplied six-item list): **enumerate the full bundle**, apply **layered static filters**, then run greedy/beam only on the **surviving** `items` dict (same simulator and scores).

Implementation: [`sim/item_heuristics.py`](sim/item_heuristics.py).

1. **Hard tag rejects** — default exclude set includes `Support`, `GoldPer`, `Consumable`, `Trinket`, `Vision` (merged with `--exclude-item-tags` on [`scripts/export_gameplay_build_orders.py`](scripts/export_gameplay_build_orders.py)). Optional **`--require-item-tags`** narrows role (e.g. `SpellDamage`).
2. **Farm mode** — **lane:** drop modern **jungle pet starters** so laners do not buy companions; **jungle:** merge **companion** item defs back from the full bundle after filtering so starters still resolve.
3. **Recipe closure** — [`downward_recipe_closure`](sim/item_heuristics.py) adds every `from_ids` component reachable from kept items so [`acquire_goal`](sim/simulator.py) can craft parents; the dict stays recipe-complete without naming preset builds.
4. **Optional static ranking** — [`modeled_dps_uplift_per_gold`](sim/item_heuristics.py) / [`rank_item_ids_by_dps_uplift_per_gold`](sim/item_heuristics.py) rank items by modeled Δ[`effective_dps`](sim/clear.py) per gold for the champion kit (single-item inventory proxy). Use for diagnostics or future top-K marginal narrowing; it does **not** replace forward `simulate`.

5. **Meaningful contribution filter + recipe closure** — [`meaningful_waveclear_exploration_catalog`](sim/item_heuristics.py) starts from the same wave-clear pool, keeps items whose modeled Δ[`effective_dps`](sim/clear.py) at a reference level exceeds a small epsilon (items that cannot move modeled farm DPS for this kit are dropped), adds **upward** prerequisites via Data Dragon `into_ids` toward surviving items, then **downward** `from_ids` closure so the shop dict stays recipe-complete. Stepwise/beam use this as the **marginal candidate allow-list** while [`simulate`](sim/simulator.py) still receives the full item map for crafting (`meaningful_exploration` on [`FarmBuildSearch`](sim/farm_build_search.py) / [`beam_refined_farm_build`](sim/greedy_farm_build.py); [`stepwise_farm_build`](sim/greedy_farm_build.py) can enable the same catalog filter via `meaningful_exploration`).

6. **Immediate farm marginal + transitive build path (bounded)** — Each purchase candidate is scored with an **immediate** term (capped farm-tick marginal per gold, or raw Δ[`effective_dps`](sim/clear.py)/gold when `marginal_income_cap=False`) plus **`path_into_weight` × [`exploration_path_value_by_item`](sim/item_heuristics.py)**. That path value is the max [`modeled_dps_uplift_per_gold`](sim/item_heuristics.py) over the item and all **`into_ids`** descendants, with an extra boost when the subtree reaches one of the top-**k** items by modeled ΔDPS (“ideal clear” proxies). Empty-prefix **horizon ROI** (`marginal_objective=horizon_greedy_roi`, default for `total_farm_gold` in [`FarmBuildSearch`](sim/farm_build_search.py)) runs **nested full simulations** (capped by `horizon_candidate_cap`) so the first buy is not ranked by myopic marginals alone.

[`export_gameplay_build_orders.py`](scripts/export_gameplay_build_orders.py) applies this pipeline **by default** (`waveclear_heuristics=on` in the header). Use **`--no-waveclear-heuristics`** to revert to manual tag filters only.

**Stat-aligned pool (optional):** [`sim/kit_stat_alignment.py`](sim/kit_stat_alignment.py) infers whether **AP** or **AD** (or **mixed**) dominates on the spell line with the largest combined scaling-per-cooldown at the reference rank, then keeps items whose flat stats plausibly feed that axis (e.g. AP + ability haste for AP carries). Pass **`--stat-align-waveclear`** on the export script to search only on that closed catalog. **`--print-modeled-dps-steps`** (or stat-align) appends a **static** per-purchase Δ[`effective_dps`](sim/clear.py) table along the reported buy order (fixed level; not a replacement for forward farm/clear sim). For ranked lists without beam search, use [`scripts/analyze_waveclear_stat_alignment.py`](scripts/analyze_waveclear_stat_alignment.py).

### From compatible stats to farm gold and clear counts

For a fixed champion and horizon, the simulator ties items to income through **one** modeling chain (see [`clear.py`](sim/clear.py), [`simulator.py`](sim/simulator.py)):

1. **Inventory** adds to [`StatBonus`](sim/models.py) via [`total_stats`](sim/stats.py).
2. **[`effective_dps`](sim/clear.py)** (lane clear DPS) increases with stats that matter for the kit (AD/AP/AS/AH, spell model, etc.).
3. **Throughput** — lane [`throughput_ratio`](sim/clear.py) and jungle route efficiency scale with clear speed vs interval until **capped**; past the cap, extra DPS does not increase the next farm tick.
4. **Totals** — [`SimResult.total_farm_gold`](sim/simulator.py), [`total_lane_minions_cleared`](sim/simulator.py), [`total_jungle_monsters_cleared`](sim/simulator.py) accumulate from those ticks.

Heuristics should prefer champion-**compatible** items whose stats actually move **`effective_dps`** in this model; saturation is the ceiling where more stats stop helping **modeled** farm/clear on the next tick.

### Heuristic pool vs preset finished-item roots

- **Default / primary:** Greedy or beam on a **heuristic-filtered** full-catalog pool (above). No **player-provided** list of six finished items is required to produce a reference export.
- **Optional diagnostic / benchmark:** [`optimal_interleaved_build`](sim/build_path_optimizer.py) and related helpers find **recipe-respecting interleaving** when **explicit finished item ids** (roots) are supplied—best for “given these six items, best purchase order,” regression tests, or comparing against catalog search. Treat that path as **supplementary**, not a prerequisite for the main wave-clear workflow.

## What `total_farm_gold` means

- **Lane:** Sum of **discrete** per-wave gold ticks when lane farming: throughput from clear time vs wave interval, **not** a continuous last-hit model.
- **Jungle:** Sum of per-route gold ticks scaled by clear speed vs base cycle time.
- **Not** a claim of matching in-game CS/sec or client-accurate combat.

**Split buckets (mode-pure runs):** [`SimResult.total_lane_minion_farm_gold`](sim/simulator.py) holds only lane wave farm ticks; [`SimResult.total_jungle_monster_farm_gold`](sim/simulator.py) holds only jungle route farm ticks. Each run uses **one** [`FarmMode`](sim/config.py), so one of these is zero and `total_farm_gold` equals their sum. Use [`primary_farm_gold_for_mode`](sim/simulator.py) when you want the active mode’s bucket explicitly. **Do not** add lane and jungle farm gold into one optimization scalar across modes (XP / jungle augment story is lane-vs-jungle separate in product terms; exact penalty math is not required in v1).

**Wallet vs farm total:** Passive gold ([`passive_gold_in_interval`](sim/passive.py)) and shop sell credits are **not** included in `total_farm_gold`. For a full breakdown and reconciliation check, use [`gold_income_breakdown`](sim/simulator.py) / [`gold_flow_reconciliation_error`](sim/simulator.py) on [`SimResult`](sim/simulator.py). The export script [`scripts/export_gameplay_build_orders.py`](scripts/export_gameplay_build_orders.py) prints per-run `gold_income_breakdown`, share percentages, and reconciliation error.

## Greedy and beam search

- **Global** maximization of `total_farm_gold` over all valid recipe-respecting purchase paths is **intractable** (huge branching factor × time horizon).
- **`stepwise_farm_build`** ([`sim/greedy_farm_build.py`](sim/greedy_farm_build.py)): minimal beam (`beam_depth=1`) using the same **immediate + transitive path** score as the beam tail ([`make_stepwise_farm_hook`](sim/greedy_farm_build.py)). When **`marginal_income_cap`** is **True** (default), the immediate term uses a first-order **farm tick** proxy on **capped** throughput ([`marginal_farm_tick.py`](sim/marginal_farm_tick.py)). **`path_into_weight`** scales the static recipe-tree signal from [`exploration_path_value_by_item`](sim/item_heuristics.py). Not globally optimal; use **`beam_refined_farm_build`** for deeper prefixes. Pass **`farm_mode`** (default **lane**) for lane vs jungle.
- **`beam_refined_farm_build`** / **`FarmBuildSearch`** ([`sim/farm_build_search.py`](sim/farm_build_search.py)): **bounded beam** over **purchase prefixes** of length up to **`beam_depth`**, keeping up to **`beam_width`** prefixes at each depth. Each leaf is a **full** `simulate` to **`t_max`** with **forced prefix** then **greedy** tail; the leaf score is `total_farm_gold` by default or **`leaf_score`** when set (e.g. **`total_clear_units`** uses [`default_clear_count_score`](sim/simulator.py)). **`max_leaf_evals`** caps total full simulations. With a **tight** budget, beam may evaluate only a few leaves (e.g. `leaves_evaluated=2`); the reported best path can **coincide with pure greedy** if no alternative prefix improves the leaf metric.
- **`marginal_objective`** (at the **empty prefix** only): **`dps_per_gold`** ranks next candidates by myopic ΔDPS/price; **`horizon_greedy_roi`** ranks them by nested full-sim **Δprimary** (farm gold or clear units per [`_leaf_primary_value`](sim/farm_build_search.py)) vs the pure-greedy baseline (extra cost; uses **`horizon_candidate_cap`** to limit candidates). For **`total_clear_units`** runs, prefer **`horizon_greedy_roi`** at the empty prefix so the first buy is not locked to myopic tick order (see **Myopic marginal equivalence** above). Deeper beam steps (non-empty prefix) use **ΔDPS/gold** marginals for tractability.

### Why “optimal” builds may not fill six item slots

**Six filled slots is not an optimization target.** The scored objective is **`total_farm_gold`** over **`t_max`**, not inventory completeness.

- **Gold vs horizon:** Over a fixed `t_max`, total income may not fund six separate valid [`acquire_goal`](sim/simulator.py) purchases at the prices in the catalog; the run can end with spare **`final_gold`** below the next affordable step.
- **Throughput cap:** Lane per-wave gold and jungle per-route gold both **cap** once clear speed reaches the modeled interval (see [`throughput_ratio`](sim/clear.py) and jungle `eff` in [`simulate`](sim/simulator.py)). After that cap, extra **modeled** DPS does not increase **`total_farm_gold`** from those ticks, even though raw **`effective_dps`** can still rise with items.
- **Greedy vs global score:** With **`marginal_income_cap`**, purchase steps prefer items that still raise **marginal farm gold per tick**; when throughput is **saturated**, `d tick_gold / d dps` is ~0 so raw DPS upgrades are skipped. That is still **not** the same as maximizing **`total_farm_gold`** globally; beam search only explores a **short forced prefix**, then the same greedy tail.
- **Modeled stats only:** If Data Dragon omits or approximates passives, an item can be strong in-client but add nothing to [`effective_dps`](sim/clear.py); the greedy loop will not “value” it.
- **Jungle:** [`FarmMode.JUNGLE`](sim/simulator.py) reserves one slot for the **companion** from starting gold. A full six-slot row is **companion + five other items**, unless you use optional **companion sell** (`jungle_sell_at_seconds`).

## Recipe validity

- Purchases must succeed under [`acquire_goal`](sim/simulator.py) (Data Dragon–style craft, sticker buy, or component buy).
- **No duplicate finished items** where rules forbid: [`ItemDef.max_inventory_copies`](sim/models.py), [`blocked_purchase_ids`](sim/simulator.py), boots tag checks—see simulator and [`ddragon_fetch`](sim/ddragon_fetch.py).
- Do **not** optimize with [`best_item_order_exhaustive`](sim/optimizer.py) over a flat list that mixes a component and its parent as independent goals unless that is intentional and documented.

## Kit and item modeling limits

- **Lane/jungle clear rate** uses [`lane_clear_dps`](sim/clear.py) (alias **`effective_dps`**): **ability** damage from Data Dragon spell JSON when [`spell_farm_model`](sim/spell_farm_model.py) parses **`cooldown`**, **`effect`** (base damage rows), and **`vars`** routed into **total vs bonus** AP and AD coefficients (see [`StatBlock`](sim/stats.py) **`bonus_attack_damage`** / **`bonus_ability_power`**). Modeled spell DPS uses per-spell **mean cooldown**, League **ability haste**, and a **mana sustain** factor when `resource_kind` is **Mana** and champion **`mpregen`** from Data Dragon is present; if regen is missing in data, sustain is not applied. **Auto-attack** clear uses **total AD** × attack speed (wiki: standard basic attacks deal **100% AD**). Optional **[`GameRules`](sim/data_loader.py)** **`lane_engagement_overhead_seconds`** / **`jungle_engagement_overhead_seconds`** shrink the effective throughput window (spawn/path/range abstraction). Spells are **independent** on-CD contributions, not a full rotation sim.
- Item **actives** and many passives are **not** modeled; stats come from Data Dragon flat stat lines on [`ItemDef`](sim/models.py).

### Components vs “full” items (deterministic)

From recipe fields alone: **[`is_build_endpoint_item`](sim/models.py)** (`into_ids` empty), **[`is_pure_shop_component`](sim/models.py)** (no `from_ids`, still upgrades), and **[`item_graph_role`](sim/models.py)** (`endpoint` | `component` | `intermediate`). That does **not** encode power level—only the shop graph.

**Components vs finished items:** The immediate term still favors **large Δ[`effective_dps`](sim/clear.py) per gold** on the snapshot; the **path** term favors buys that sit on **`into_ids`** routes toward high modeled-clear finishers. Near **throughput saturation**, immediate marginals shrink; path value still rewards components that complete toward strong upgrades. Use **`endpoints_only_marginals`** in [`beam_refined_farm_build`](sim/greedy_farm_build.py) / export scripts to restrict candidate purchases, or **tag filters** ([`item_tag_filters`](sim/item_tag_filters.py)) for catalog policy.

### Resolving a champion display name to a bundle id

[`resolve_champion_key_for_version`](sim/ddragon_fetch.py)(`"Lee Sin"`, patch) → Data Dragon id (e.g. `LeeSin`) using the same **`champion.json`** index as [`champion_json`](sim/ddragon_fetch.py). Use that string as `champion_id` in [`simulate`](sim/simulator.py) when the bundle was built from that patch.

## Parameters (defaults for scripts)

| Parameter | Typical value | Role |
|-----------|---------------|------|
| `t_max` | `3600` | Horizon (seconds) |
| `epsilon` | `1e-9` | Avoid division by zero in marginal score |
| `beam_depth` `D` | `1` | Prefix layers to branch (deeper = more search, slower) |
| `beam_width` `B` | `3` | Prefixes retained per depth |
| `max_leaf_evals` | `27` | Cap on full `simulate` calls in beam search |
| `farm_mode` | `LANE` | `LANE` = minion waves; `JUNGLE` = camp routes |
| `marginal_objective` | `dps_per_gold` (except `export_gameplay_build_orders.py` defaults `horizon_greedy_roi` when `leaf_score=total_clear_units`) | `horizon_greedy_roi` at empty prefix only (costly) |
| `marginal_income_cap` | `True` | Use capped-throughput farm-tick derivative for greedy marginal score |
| `eta_lane` | `1.0` | Lane throughput factor |

## Post-hoc checks

After a run, [`clear_upgrade_report`](sim/marginal_clear.py) tries each catalog item once via [`acquire_goal`](sim/simulator.py) on a snapshot of **`final_gold`**, **`final_inventory`**, and a reconstructed [`blocked_purchase_ids_from_inventory`](sim/simulator.py) set (same duplicate rules as the live sim). Rows list acquisitions that succeed and increase **modeled** **`effective_dps`**, with **actual gold paid** (sticker, recipe fee, or component cost) in the third field. It does **not** prove global farm optimality; it signals whether another **valid one-step shop action** would raise DPS at the final snapshot.
