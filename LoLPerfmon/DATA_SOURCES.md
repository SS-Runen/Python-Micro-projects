# Data sources hierarchy (LoLPerfmon)

Simulation code under `LoLPerfmon/sim/` follows this order. **Riot Data Dragon** is authoritative when network and a patch version are available ([Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon)).

| Priority | Source | Role |
|----------|--------|------|
| **1** | **Data Dragon** CDN JSON (`versions.json`, `item.json`, `champion/{id}.json`) | Default for items, champion stats, spells/passive fields. |
| **2** | **League of Legends Wiki** (human reference) | Optional **curated** tables or manual exports **only** when Data Dragon is incomplete or not machine-parsed. **No** automated HTML scraping in `sim/`. |
| **3** | **Local SR rules** (`summoners_rift_rules.py`, `minion_defaults.py`, `wave_schedule.py`) | Documented constants (passive gold cadence, waves, XP curve) — not a substitute for DD item/champion blobs. |
| **4** | **Offline bundle** (`build_offline_bundle`: `generic_ap`, `cheap_ap` / `cheap_ad`) | **CI / no-network / DD failure only.** Not patch-accurate; do not treat as live balance. |

Modules: `ddragon_fetch.py` (CDN loads; champion ids resolved via per-patch `champion.json` so display names and internal ids like `MonkeyKing`/`Wukong` align), `ddragon_availability.py` (key coverage audit), `ddragon_spell_parse.py` (cooldowns, costs, vars), `bundle_factory.get_game_bundle_with_audit` (bundle + audit report).

Wiki or repo YAML must **never** override official JSON when Data Dragon is available for the same fact.

## Unconstrained farm / clear-speed optimization

Normative scoring and anti-patterns (what to maximize, greedy vs beam, kit limits): [`OPTIMIZATION_CRITERIA.md`](OPTIMIZATION_CRITERIA.md).

- **`greedy_farm_build`** / **`beam_refined_farm_build`** ([`sim/greedy_farm_build.py`](sim/greedy_farm_build.py)): full SR catalog (via bundle loading) with recipe-valid **`acquire_goal`** purchases; greedy uses **Δeffective_dps / gold** locally; beam (depth 1) tries top-**B** first purchases from ranked marginals at **t=0** plus the pure greedy baseline. Primary comparison metric remains **`total_farm_gold`** on :class:`~LoLPerfmon.sim.simulator.SimResult`.
- **`simulate(..., lane_purchase_hook=...)`** ([`sim/simulator.py`](sim/simulator.py)): lane-only hook replaces fixed `PurchasePolicy` queue draining for custom shop logic.
- **`lane_clear_dps`** ([`sim/clear.py`](sim/clear.py)): minion/jungle clear rate from parsed spell rotation + optional autos; greedy search uses **Δlane_clear_dps** (still labeled `effective_dps` as an alias).

## Testing Data Dragon code

Guidelines for meaningful pytest coverage and validation (frozen excerpts, independent oracles, no tautological kit assertions): [`LoLPerfmon/tests/README_DATA_DRAGON.md`](tests/README_DATA_DRAGON.md).

## Build optimization vs recipe expansion

- **`best_item_order_exhaustive`** ([`sim/optimizer.py`](sim/optimizer.py)): permutes a **flat tuple of goal item ids**. Each id is one **independent** queued purchase. It does **not** expand “Luden’s Echo” into Lost Chapter + NLR + …; listing a **component and its parent** as separate goals is usually **wrong** (redundant slots, wrong craft ordering).
- **`acquisition_postorder_for_item`** + **`optimal_interleaved_build`** ([`sim/build_path_optimizer.py`](sim/build_path_optimizer.py)): each **finished-item root** is expanded along Data Dragon **`from_ids`** (DFS post-order), then sequences are **interleaved** or block-permuted. Components like NLR appear only as steps toward a root (e.g. Luden’s), not as unrelated terminal goals.
- **`acquisition_sequence_for_finished_roots`**: concatenates post-orders for roots in order (helper when you do not need interleaving search).

Use **finished roots** + recipe expansion for “max clear” builds; reserve exhaustive permutation for small sets of **intentionally independent** items (e.g. three mythics). **Selling items is not modeled**; the sim assumes purchases follow a coherent path.

Post-run **marginal clear** checks: [`sim/marginal_clear.py`](sim/marginal_clear.py) (`clear_upgrade_report`).
