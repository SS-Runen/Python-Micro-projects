# Data sources hierarchy (LoLPerfmon)

Simulation code under `LoLPerfmon/sim/` follows this order for **Classic Summoner’s Rift 5v5** (align with wiki filter “Classic SR 5v5” and Data Dragon `maps` where applicable). **Riot’s documentation and static CDN JSON** outrank local placeholders.

| Priority | Source | Role |
|----------|--------|------|
| **1** | **[Riot developer docs](https://developer.riotgames.com/docs/lol)** + **Data Dragon** CDN JSON (`versions.json`, `item.json`, `champion/{id}.json`) | Authoritative patch versions, item/champion blobs, SR availability via `maps`, spell `effect`/`vars`. |
| **2** | **Riot game APIs** (match/timeline, etc.) | Only if a feature needs **live** match data; static optimization uses Data Dragon. Respect [API key tiers and app registration](https://riot-api-libraries.readthedocs.io/en/latest/applications.html) when calling Riot APIs. |
| **3** | **Community mirrors** of Data Dragon | Convenience only; **numeric ground truth** must match the official CDN JSON. |
| **4** | **[League of Legends Wiki](https://wiki.leagueoflegends.com/en-us/Item)** (e.g. items, uniqueness, boots) | Human-readable rules and cross-checks when Data Dragon does not encode a behavior the sim enforces. **Do not** override Data Dragon numbers when they conflict. |
| **5** | **Local SR rules** (`summoners_rift_rules.py`, `minion_defaults.py`, `wave_schedule.py`) | Documented constants (passive cadence, waves, XP curve); prefer values traceable to official design posts/patch notes where possible. |
| **6** | **Offline bundle** (`build_offline_bundle`) | **CI / no-network / DD failure only.** Not patch-accurate; labeled placeholder. Prefer **frozen** committed excerpts or CI-cached Data Dragon JSON when tests must be reproducible; avoid inventing numeric stand-ins for Riot-sourced fields when policy requires “no local fake stats.” |

Modules: `ddragon_fetch.py` (CDN loads; SR classic map id `11`; optional **ranked/draft** item filter via `item_eligible_ranked_summoners_rift_5v5` on full catalogs), `ddragon_availability.py`, `ddragon_spell_parse.py`, `bundle_factory.get_game_bundle_with_audit`.

**Skill-point tuples:** Data Dragon supplies per-spell `maxrank` and slot order, not a list of legal rank assignments. [`skill_order_reachability.py`](sim/skill_order_reachability.py) encodes Classic SR reachability (levels 1–3 basics, R at 6/11/16) for [`spell_farm_model.py`](sim/spell_farm_model.py) waveclear DPS.

Wiki or repo YAML must **never** override official JSON when Data Dragon is available for the same fact.

## Unconstrained farm / clear-speed optimization

Normative scoring: [`OPTIMIZATION_CRITERIA.md`](OPTIMIZATION_CRITERIA.md).

- **`stepwise_farm_build`** / **`beam_refined_farm_build`** / **`FarmBuildSearch`** ([`sim/greedy_farm_build.py`](sim/greedy_farm_build.py), [`sim/farm_build_search.py`](sim/farm_build_search.py)): recipe-valid **`acquire_goal`** purchases; **`farm_mode`** selects **lane** (waves) vs **jungle** (camp cycles) exclusively. Stepwise purchases rank **immediate** farm marginals plus **transitive** `into_ids` path value toward high modeled-clear items ([`exploration_path_value_by_item`](sim/item_heuristics.py)); beam search branches **prefixes** up to **`beam_depth`** × **`beam_width`** with **`max_leaf_evals`** cap. Primary metric: **`total_farm_gold`** on [`SimResult`](sim/simulator.py).
- **`simulate(..., purchase_hook=...)`** ([`sim/simulator.py`](sim/simulator.py)): optional hook at each purchase point for **lane or jungle** (replaces draining `PurchasePolicy` when set). **`lane_purchase_hook`** is a deprecated alias for **`purchase_hook`**.
- **`lane_clear_dps`** ([`sim/clear.py`](sim/clear.py)): minion/jungle clear rate; greedy marginals use **Δeffective_dps**.

## Testing Data Dragon code

Guidelines for meaningful pytest coverage and validation (frozen excerpts, independent oracles, no tautological kit assertions): [`LoLPerfmon/tests/README_DATA_DRAGON.md`](tests/README_DATA_DRAGON.md).

## Build optimization vs recipe expansion

- **`best_item_order_exhaustive`** ([`sim/optimizer.py`](sim/optimizer.py)): permutes a **flat tuple of goal item ids**. Each id is one **independent** queued purchase. It does **not** expand “Luden’s Echo” into Lost Chapter + NLR + …; listing a **component and its parent** as separate goals is usually **wrong** (redundant slots, wrong craft ordering).
- **`acquisition_postorder_for_item`** + **`optimal_interleaved_build`** ([`sim/build_path_optimizer.py`](sim/build_path_optimizer.py)): each **finished-item root** is expanded along Data Dragon **`from_ids`** (DFS post-order), then sequences are **interleaved** or block-permuted. Components like NLR appear only as steps toward a root (e.g. Luden’s), not as unrelated terminal goals.
- **`acquisition_sequence_for_finished_roots`**: concatenates post-orders for roots in order (helper when you do not need interleaving search).

Use **finished roots** + recipe expansion for “max clear” builds; reserve exhaustive permutation for small sets of **intentionally independent** items (e.g. three mythics). **Selling** is modeled deterministically: [`sell_item_once`](sim/simulator.py) credits **50%** of `ItemDef.total_cost` ([`shop_sell_refund_gold`](sim/sell_economy.py)); greedy hooks may sell lane starters and, with `allow_sell_non_starter_items`, other items to afford the next buy.

Post-run **marginal clear** checks: [`sim/marginal_clear.py`](sim/marginal_clear.py) (`clear_upgrade_report`).

## Wiki alignment (farm model scope)

| Wiki topic | URL | In-repo behavior |
|------------|-----|-------------------|
| **Jungling** (jungle items, pets) | [Jungle items](https://wiki.leagueoflegends.com/en-us/Jungling#Jungle_items) | Companion from Data Dragon `Jungle` tag at `t=0`; treat evolution / Smite tiers **not** simulated—only stats on `ItemDef`. Optional companion sell timing via `simulate(..., jungle_sell_at_seconds=...)`. |
| **Farming** (CS, lane income) | [Farming](https://wiki.leagueoflegends.com/en-us/Farming) | Lane: **wave throughput** (`throughput_ratio` × wave gold), not per-minion last-hit RNG. Shared lane CS / proxy freeze not modeled. |
| **Experience** (champion) | [Experience](https://wiki.leagueoflegends.com/en-us/Experience_(champion)) | Lane XP from minion tables × same throughput fraction as gold; **no** XP from champion kills or objectives unless added to rules. |

Full assumption list: [`OPTIMIZATION_CRITERIA.md`](OPTIMIZATION_CRITERIA.md) (Modeling assumptions).
