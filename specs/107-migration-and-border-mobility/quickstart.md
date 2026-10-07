# Quickstart: Migration and Border Mobility

## Prerequisites

- Run from the repository root in PowerShell.
- Use the repository virtual environment: `.venv\Scripts\python.exe`.
- Migration performance measurement is opt-in; functional tests run without the environment variable.

## Focused verification

```powershell
.venv\Scripts\python.exe -m pytest `
  tests/test_migration_policy.py `
  tests/test_migration_system.py `
  tests/test_migration_integration.py `
  tests/test_migration_ai_policy.py `
  tests/test_migration_presenter.py `
  tests/test_ai_policies.py `
  tests/test_migration_performance.py `
  tests/test_population_system.py `
  tests/test_economic_health_integration.py `
  tests/test_economic_health_ai_policy.py `
  tests/test_economic_health_system.py `
  tests/test_economic_health_policy.py `
  tests/test_economic_health_performance.py `
  tests/test_economic_health_presenter.py `
  tests/test_treaty_specification.py `
  tests/test_treaty_rules.py `
  tests/test_treaty_trade_policy.py `
  tests/test_schema_mod_migrations.py `
  tests/test_runtime_architecture.py `
  tests/test_layer_boundaries.py `
  tests/test_infrastructure_integration.py `
  tests/test_infrastructure_policy.py `
  tests/test_regional_infrastructure_system.py `
  tests/test_infrastructure_presenter.py `
  tests/test_infrastructure_ai_policy.py `
  tests/test_headless_server.py::TestHeadlessServer::test_launcher_client_proxy_executes_command_over_delta_ipc -q -p no:cacheprovider
```

Recorded result on Windows/Python 3.14.1 after the latest integration changes: `135 passed, 2 skipped, 116 warnings, 5 subtests passed in 44.08s`. The skips are the opt-in economic-health and migration performance gates; both were also run explicitly with their environment variables.

The focused suite should cover these user-visible checks:

1. Same-country adjacent regions can create a domestic flow; non-adjacent unsupported routes cannot.
2. Cross-country flows obey both countries’ current policies, explicit mobility treaty effects, active sanctions, wars, and current ownership.
3. Pending flows do not mutate cohorts; completion transfers exact integer cohorts and preserves world totals.
4. Effective-dated policy actions enforce authority, defaults, finite bounds, and transition rules for in-flight flows.
5. Empty regions accept population only when ownership, access, housing, employment, transport, and services are eligible; births remain unrelated.
6. Capacity and cohort shortages are capped; simultaneous pending flows reserve capacity, and an authorized flow reroutes to a connected eligible neighbor when its original destination no longer has room.
7. Politics and economic-health consumers use the same flow signal once per window without duplicate effects.
8. AI policy actions pass through the same flow rules as player actions; the presenter exposes policy, net migration, top routes, and capacity reasons.
9. Old save schemas gain empty/default migration state while preserving region cohorts; new saves, snapshots, and replay preserve pending/completed flow state.
10. Identical initial state and ordered actions produce identical policies, flow rows, events, signals, and final cohorts across three runs.
11. A capacity reroute records a terminal `redirected` route and a linked pending route without changing population before the redirected arrival completes.

## Controlled performance gate

```powershell
$env:RUN_MIGRATION_BENCHMARKS = '1'
.venv\Scripts\python.exe -m pytest tests/test_migration_performance.py -q -s -p no:cacheprovider
Remove-Item Env:RUN_MIGRATION_BENCHMARKS
```

The gate generates 10,000 pending records against a fixed world snapshot, resolves only due flows, and asserts elapsed system time below 250 ms on the current controlled environment. It also reports the exact fixture size, due count, and elapsed time. Do not compare timings across unlike machines as a correctness result.

Latest controlled result: `10,000 pending flows, 100 due; 0.093s` (`1 passed`), under the 250 ms target.

## Cross-feature compatibility gate

```powershell
.venv\Scripts\python.exe -m pytest `
  tests/test_migration_policy.py `
  tests/test_migration_system.py `
  tests/test_migration_integration.py `
  tests/test_migration_ai_policy.py `
  tests/test_migration_presenter.py `
  tests/test_population_system.py `
  tests/test_economic_health_integration.py `
  tests/test_economic_health_ai_policy.py `
  tests/test_economic_health_system.py `
  tests/test_economic_health_policy.py `
  tests/test_economic_health_presenter.py `
  tests/test_treaty_specification.py `
  tests/test_treaty_rules.py `
  tests/test_treaty_trade_policy.py `
  tests/test_schema_mod_migrations.py `
  tests/test_runtime_architecture.py `
  tests/test_layer_boundaries.py `
  tests/test_infrastructure_integration.py `
  tests/test_infrastructure_policy.py `
  tests/test_regional_infrastructure_system.py `
  tests/test_infrastructure_presenter.py `
  tests/test_infrastructure_ai_policy.py -q -p no:cacheprovider
```

PowerShell does not expand pytest filename globs such as `tests/test_migration_*.py`; list test files explicitly so the command works consistently from the repository root.

## Repository-wide regression status

```powershell
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

The historical repository suite reported `524 passed, 4 skipped, 116 warnings, 173 subtests passed in 151.51s` on Windows/Python 3.14.1. The four then-default skips were controlled economic-health, infrastructure, migration, and recognition scale benchmarks; all four passed separately with their documented opt-in flags. The latest repository-wide run reports `684 passed, 16 skipped, 116 warnings, 190 subtests passed in 162.89s` (2026-10-07). The previously slow real-session save/load round-trip passed within the full suite and in isolation (`1 passed, 168 subtests passed in 41.45s`). The latest migration controlled benchmark completed at 0.093s. T036 is complete. Interactive migration-panel scenarios remain unverified and are not inferred from headless tests.

UI verification additionally requires an interactive client session: inspect a selected populated region and an eligible empty region, verify flow status/reason and current policy, change one policy through the panel, and confirm that it is sent as a semantic action and becomes effective only at its recorded minute. Headless presenter tests do not claim this visual check.
