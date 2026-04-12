# Data Dragon tests (meaningful coverage)

This matches the widened **Data Dragon availability** plan: official CDN JSON is authoritative; tests should prove parsers and audits behave correctly **without** assuming unrelated code is correct.

## What “good” looks like

1. **Frozen payloads**  
   Prefer **verbatim excerpts** from Riot’s CDN (`/cdn/<patch>/data/en_US/...`) stored in `LoLPerfmon/sim/ddragon_sample_payloads.py` with the patch version in the module docstring. Do not embed invented `vars` / stats in a “real” excerpt to force a parser branch; use a **minimal inline dict** in the test file when you need to isolate one missing key or one `vars` entry.

2. **Independent oracles**  
   - **Cooldown → DPS hook:** assert `kit.base_ability_dps` equals `base_ability_dps_hint_from_mean_cooldown(mean_cd)` where `mean_cd` is computed with **plain arithmetic on the JSON list** in the fixture, not by re-reading `ParsedSpell` internals.  
   - **Unmapped stats:** assert an item id is flagged because a stat **name** is provably absent from `ITEM_STATS_KEYS_MAPPED`, not because the test hardcodes the same list as production in a tautology.  
   - **ItemDef:** assert `total_cost` and mapped stats match **the fixture’s** `gold.total` / `FlatMagicDamageMod` so the test checks wiring from JSON → model.

3. **Table-driven pure functions**  
   `base_ability_dps_hint_from_mean_cooldown` is public and covered with **parametrized** expectations (boundary clamps). That tests the numeric contract directly instead of encoding “Lux should be AP-heavy” by re-asserting `_KIT_OVERRIDES`.

4. **What to avoid**  
   - Assertions that only mirror the same constant or formula stored next to the test (e.g. “Lux has `ap_weight > ad_weight`” without an external contract).  
   - Mocking or stubbing **our** parsers/audits to return success.  
   - Fake “integration” tests that patch `champion_json` to return a hand-waved dict without documenting patch/version.

5. **Network**  
   Live CDN calls belong in **`@pytest.mark.integration`** (see `test_recipe_ddragon_integration.py`, `test_e2e.py`). Default CI stays offline (`LOLPERFMON_OFFLINE=1`).

6. **Validation CLI**  
   `python -m LoLPerfmon.validation_checks` runs `LoLPerfmon.sim.ddragon_fixture_checks.verify_frozen_sample_payloads()` so the same assertions apply outside pytest.

7. **Simulator**  
   End-to-end gold/stat behavior with a real `GameDataBundle` stays in `test_simulator.py`, `test_e2e.py`, and integration tests — not in the DD parser unit tests.

8. **Champion ids**  
   `champion.json` maps internal ids (e.g. `MonkeyKing`) to display names (`Wukong`). Resolution is tested with a **minimal** `champion.json`-shaped dict in `test_champion_ddragon_index.py` (no network). Live CDN integration can still use `@pytest.mark.integration`.

9. **Build APIs**  
   Do not use `best_item_order_exhaustive` with a mix of **components and parents** (e.g. NLR + Luden’s) as peer goals—use **`optimal_interleaved_build`** / **`acquisition_postorder_for_item`** with **finished-item roots** so the recipe graph is respected. See `DATA_SOURCES.md` § Build optimization vs recipe expansion.

See also `LoLPerfmon/DATA_SOURCES.md` and `.cursor/rules/testing-standards.mdc`.
