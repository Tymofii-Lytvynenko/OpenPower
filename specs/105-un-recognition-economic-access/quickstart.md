# Quickstart: Recognition and Regional Economic Access

## Regional production data contract

Regional output is optional and must be authored explicitly in the country resource TOML. The region key should use its `iso_region` identifier:

```toml
[resources.cereals]
production = 100.0

[regional_resources."AA-X01".cereals]
production = 40.0
```

`regional_production` stores the explicit source region, country, resource, and production amount. The region key must resolve to exactly one loaded region. Each regional amount is a declared subset of the corresponding national resource total; it must be finite, non-negative, and no greater than that total. National resource aggregates are never apportioned across regions.

Trade rows backed by these records carry `source_region_id`. If the source region has an active recognition case, foreign bilateral access requires a current recognized status and the producing country must still own and control the region. Ordinary regions without an active recognition claim retain the existing trade behavior. When no regional source records are loaded, the existing national market path is unchanged.

## Focused validation

Run from the repository root using the project virtual environment:

```powershell
$env:RUN_RECOGNITION_BENCHMARKS = "1"
.\.venv\Scripts\python.exe -m pytest -q tests/test_recognition_system.py tests/test_recognition_presenter.py tests/test_recognition_persistence.py tests/test_recognition_performance.py tests/test_regional_recognition_trade.py tests/test_treaty_rules.py tests/test_treaty_trade_policy.py tests/test_treaty_specification.py tests/test_diplomacy_system.py tests/test_weapons_trade.py tests/test_data_loader_mod_layering.py tests/test_schema_mod_migrations.py tests/test_layer_boundaries.py tests/test_migration_system.py tests/test_economy_smoke.py
```

The matrix covers case/vote lifecycle, recognition access, explicit region-source loading, provenance-preserving flows, treaty constraints, save/snapshot continuation, schema migration, and layer boundaries.

## Full repository check

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Validation on Windows / Python 3.14.1 / project virtual environment: the focused recognition matrix passed with **51 passed in 11.19 s**, including the opt-in recognition scale gate (**1,000 pending cases, 10,000 votes, 10,000 statuses; 0.052 s**); a fresh standalone controlled run measured **0.061 s**. The historical full-suite run at T013 reported **524 passed, 4 skipped, 173 subtests passed in 151.51 s**; the four then-skipped opt-in benchmarks all passed separately, and the suite exercised the real-session save/load round-trip. The latest repository-wide run reports **917 passed, 25 skipped, 116 warnings, 239 subtests passed in 832.53 s** (2026-10-07). T013 is complete; interactive diplomacy/region-inspector visual checks remain separate manual acceptance work.

National-only production and financial records without source-region provenance are deliberately not attributed to a region. This avoids guessing regional origin; the current recognition gate applies before applying explicitly source-tagged regional trade. Any future region-sourced financial, tax, or treaty-benefit flow must preserve its source region and call the same access policy.
