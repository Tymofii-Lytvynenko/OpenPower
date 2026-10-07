# Quickstart: Economic Health and Debt Failure

## Focused validation

From the repository root, run the policy, lifecycle, integration, persistence, and affected-system regressions:

```powershell
.venv\Scripts\python.exe -m pytest `
  tests/test_economic_health_policy.py `
  tests/test_economic_health_system.py `
  tests/test_economic_health_integration.py `
  tests/test_economic_health_ai_policy.py `
  tests/test_economic_health_presenter.py `
  tests/test_economic_health_performance.py `
  tests/test_economy_smoke.py `
  tests/test_weapons_trade.py `
  tests/test_treaty_trade_policy.py `
  tests/test_military_maintenance_budget.py `
  tests/test_diplomacy_system.py `
  tests/test_diplomatic_aid.py `
  tests/test_ai_system.py `
  tests/test_ai_integration.py `
  tests/test_ai_framework.py `
  tests/test_ai_policies.py `
  tests/test_schema_mod_migrations.py `
  tests/test_layer_boundaries.py `
  tests/test_migration_integration.py -q -p no:cacheprovider
```

The focused suite verifies bounded indicators and action rejection, effective-time and cooldown behavior, treasury conservation, repeated overdue payments, arrears/default/restructuring/recovery, deterministic ordering, legacy schema seeding, snapshot and actual save/load round-trips, read-only presentation, AI actions, and affected economy/diplomacy/layer boundaries. Migration flow is implemented; migration labor/service signals are consumed once by the economic-health lifecycle and covered by the migration/economic integration suites.

Run the controlled 10,000-country / 100,000-contract benchmark separately:

```powershell
$env:RUN_ECONOMIC_HEALTH_BENCHMARKS = "1"
.venv\Scripts\python.exe -m pytest tests/test_economic_health_performance.py -q -s -p no:cacheprovider
```

## Manual client scenario

1. Start a single-player scenario and select a country with economic-policy authority.
2. Inspect health, minimum wage, interest, inflation, employment, poverty, treasury/balance, debts, next service date, risk causes, and current recovery requirements.
3. Submit a valid minimum-wage or interest change; verify the displayed effective minute and that the value changes only after that boundary. Submit an invalid/out-of-bounds value and confirm no authoritative state changes.
4. Request financing from an existing country. Before creditor approval, confirm no reserves move. Approve as the creditor and confirm principal transfers once and the schedule is visible to both sides.
5. Advance to a payment date with insufficient debtor reserves. Confirm only available funds transfer, unpaid service becomes arrears, and distress restrictions remain bounded and visible.
6. Improve the fiscal/health conditions or restructure under the configured policy; verify the recovery transition and removal of only eligible restrictions.
7. Save, reload, and compare policy timers, obligation schedule, arrears, distress status, and recent causes.

## Evidence boundary

Headless automated tests establish simulation, persistence, and performance behavior. The manual scenario is required for visual acceptance and remains unverified in headless validation. Migration flows are implemented in the demographics domain; economic-health integration consumes their persisted service/labor signals once per eligible update, covered by the migration and economic-health integration tests.

## Validation results

Validated on Python 3.14.1 / Windows 11:

- Focused economic, diplomacy, AI, migration, persistence, and layer-boundary regressions: **92 passed, 1 opt-in benchmark skipped, 5 subtests passed in 13.54 seconds**. The opt-in scale gate was run separately.
- Snapshot and actual Parquet save/load round-trips preserved country indicators, policy transitions, debt schedule and arrears, distress cases, and cause history.
- Latest controlled scale gate: **10,000 countries, 100,000 contracts, 100 due contracts; 0.060 seconds** (under the 1-second target). Due contracts are processed chronologically while country balance changes and cause rows are batched; the benchmark's exact due-row count remains verified.
- Historical repository suite: **524 passed, 4 opt-in skips, 173 subtests passed in 151.51 seconds**. All four scale gates then skipped by default (economic health, infrastructure, migration, recognition) passed in a separate controlled run. The latest repository-wide run reports **684 passed, 16 skipped, 116 warnings, 190 subtests passed in 162.89 seconds** (2026-10-07).
- Interactive client validation remains unverified; it is not inferred from presenter or headless tests.
