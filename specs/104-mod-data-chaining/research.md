# Implementation Evidence: Mod Data Chaining

## Compatibility metadata

`mods.json` selects the active roots; each module's `mod.toml` declares its dependency list and optional `min_engine_version` / `max_engine_version` bounds. The engine version is read from the source project's `pyproject.toml` (with a packaged fallback). `ModManager.load_runtime()` validates every resolved module before importing registrations or allowing session startup to allocate/load world state. Bounds use numeric `MAJOR.MINOR.PATCH` versions.

## Cascading assets and localization

Assets continue to resolve from highest-priority active mod to the base fallback through `GameConfig.get_asset_path()`. Flat JSON localization catalogs at `assets/localization/<locale>.json` merge from base to active-mod order; a later mod overrides a key while retaining unrelated base strings. Catalogs must contain string keys and string values.

## Performance gate SC-001

## Layered identity profile evidence

`StaticAssetLoader.load_country_identity_distribution()` reads the language and religion profile files through the active module chain, drops rows for countries not in the loaded world, rejects invalid/non-positive shares, and normalizes each accepted profile. A valid nonempty profile in a later layer replaces the earlier profile for the same country and identity dimension. The production `DataLoader` loads this table before schema initialization and bootstrap seeding. `tests/test_data_loader_mod_layering.py` covers layered replacement, normalized shares, and the unknown-year marker. Keyed extension tests also assert repeated keys collapse rather than multiply a region record.

`tests/test_mod_data_chaining_performance.py` creates a deterministic 25-mod dependency chain. Each layer contributes records to the same world table; the scenario measures dependency resolution and Polars table merging after one warm-up, then checks load order, appended records, and highest-priority override behavior.

| Samples (ms) | Median | Gate |
|---|---:|---|
| 20.98, 31.04, 20.06, 18.50, 18.44 | 20.06 ms | Pass (<1,500 ms) |
| 18.84, 17.80, 18.51, 18.54, 18.72 | 18.54 ms | Pass (<1,500 ms) |

The controlled runs used `POLARS_MAX_THREADS=1`. The latest run used Python 3.14.1 and Polars 1.36.1 on Windows 11 with 25 mods; all five samples are recorded above. No performance optimization was required.

## Verification

Functional checks:

```powershell
$env:POLARS_MAX_THREADS = '1'
python -m pytest -q tests/test_mod_manager.py tests/test_game_config.py tests/test_data_loader_mod_layering.py tests/test_mod_startup_performance.py
```

The latest targeted run passed 49 tests; one opt-in cold-start benchmark was skipped. It covered mod manifests and compatibility, config/asset resolution, data layering, startup/session allocation order, system registration, schema migrations, and layer boundaries.

Run the 25-mod performance gate with:

```powershell
$env:POLARS_MAX_THREADS = '1'
$env:RUN_MOD_CHAIN_BENCHMARKS = '1'
python -m pytest -s -q tests/test_mod_data_chaining_performance.py
```
