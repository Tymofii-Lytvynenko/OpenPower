# Quickstart: Regional Infrastructure and Telecommunications

## Prerequisites

- Python dependencies installed in the repository environment.
- A loaded base world with regions and countries.
- For interactive validation, a country with positive treasury and a region it currently owns.

## Focused automated validation

From the repository root:

```powershell
$env:RUN_INFRASTRUCTURE_BENCHMARKS = "1"
.venv\Scripts\python.exe -m pytest `
  tests/test_infrastructure_policy.py `
  tests/test_infrastructure_ai_policy.py `
  tests/test_regional_infrastructure_system.py `
  tests/test_infrastructure_integration.py `
  tests/test_infrastructure_presenter.py `
  tests/test_infrastructure_performance.py `
  tests/test_military_route_policy.py `
  tests/test_strategic_warfare_system.py `
  tests/test_schema_mod_migrations.py `
  tests/test_layer_boundaries.py -q -p no:cacheprovider
```

Expected outcomes:

- missing profile tables are initialized deterministically from legacy regional values or configured baselines without changing existing population, GDP, or treasury;
- a valid investment reserves funds once, advances on game time, and changes only its selected region/category when completed;
- invalid ownership, category, target, duplicate active project, or insufficient-funds actions create no partial debit or capacity change and report a reason;
- depreciation and maintenance remain within bounds; source-attributed damage is idempotent and reconstruction respects its ceiling;
- route duration and command coordination, production/development modifiers, and telecom-dependent information quality read the regional modifiers rather than a national average;
- saving/loading and repeated seeded runs preserve projects, damage history, condition, and aggregate values;
- 100,000 regional-category profiles with 1% changed meet the documented one-second controlled benchmark.

## Interactive validation

1. Select a country and an owned region; inspect all four infrastructure categories and the current national aggregates.
2. Submit an investment below the configured maximum with sufficient treasury. Confirm the treasury change, quoted cost, project status, progress, and reason.
3. Attempt the same investment with an unowned region, unsupported category, already-active category project, over-maximum target, and insufficient treasury. Each must be rejected without a partial debit.
4. Advance game time until completion. Confirm only the selected regional category improves, then compare movement/production/service/intelligence readouts in that region and an unaffected region.
5. Change control of a region with an active project, then restore control. Confirm the project pauses without progress while control is lost and resumes when the original funding country regains control; cancel another active project and confirm its uncompleted share is refunded.
6. Apply strategic or disaster damage to one category, save/load while reconstruction is pending, and confirm cause, current condition, and restoration ceiling remain stable.

## Validation results

Focused validation on Python 3.14.1 / Windows 11: 46 tests passed and 116 third-party pyglet deprecation warnings. Snapshot IPC and save/load round trips passed in `test_partial_legacy_tables_snapshot_and_save_load_preserve_infrastructure_state`. Latest controlled incremental gate: 100,000 regional-category profiles (25,000 regions × 4 categories), 1,000 changed profiles (1%), and 250 affected regional projections in **0.051 seconds**. The historical complete repository suite reported 524 tests and 173 subtests, with four opt-in scale benchmarks run separately and passed. The latest repository-wide run reports **684 passed, 16 skipped, 116 warnings, 190 subtests passed in 162.89 seconds** (2026-10-07).

Interactive client scenarios were not run in this headless validation. Before release, verify the selected-region panel, action feedback, and downstream HUD/map presentation in a running client; do not infer visual usability from presenter unit tests.
