# Quickstart: Geo-Coordinated Military Movement

## Automated validation

From the repository root, run the relevant policy, readiness, invasion, and client-projection suites:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_military_route_policy.py `
  tests/test_movement_access.py `
  tests/test_naval_invasion_policy.py `
  tests/test_order_readiness.py `
  tests/test_military_route_presenter.py `
  tests/test_unit_route_overlay.py `
  tests/test_military_movement_spec.py `
  tests/test_region_route_snapshot.py `
  tests/test_region_travel_time.py `
  tests/test_military_movement_performance.py
```

The suite should verify distance/duration formulas, deterministic route and tie-break behavior, legal access, rejected-order immutability, waypoint timing, readiness queuing, per-group order outcomes, invasion boundary checks, and route presentation.

Run the complete regression suite with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The opt-in 10,000-unit benchmark is run separately so its timing is recorded without making the standard suite hardware-flaky:

```powershell
$env:RUN_MILITARY_MOVEMENT_BENCHMARKS = '1'
.\.venv\Scripts\python.exe -m pytest -q tests/test_military_movement_performance.py
```

Measured on 2026-10-07: Windows 11 (10.0.26200), CPython 3.14.1, Polars 1.36.1, NumPy 2.2.6, AMD64 Family 23 Model 8 processor as reported by the runtime. The workload used 10,000 units, 4,561 regions, and 200 owner tags; after five warmups, 101 measured samples produced these medians/p95 values:

| Workload | Median | p95 |
| --- | ---: | ---: |
| Stationary movement + manpower | 0.375 ms | 0.387 ms |
| In-transit movement + manpower | 1.138 ms | 1.214 ms |

Both measured cases satisfy the `<2 ms` target on this runtime. This is a local empirical result, not a guarantee for other hardware; rerun the opt-in benchmark on the target deployment machine before release.

## Recorded automated outcomes

Final focused movement/client-projection validation with the opt-in benchmark enabled: `45 passed, 3 subtests passed in 2.09s`. Latest repository suite: `684 passed, 16 skipped, 116 warnings, 190 subtests passed in 162.89s` (2026-10-07). The 116 warnings are the existing Pyglet `ctypes._pointer_type_cache` deprecation warning; the standard suite has no test failures.

## Manual client validation

In a running single-player scenario, issue movement to a selected group and to a multi-selection containing both legal and illegal destinations. Confirm each unit has independent route/status/ETA, the route appears with the existing affiliation colors, and rejected groups preserve coordinates and readiness. Change a transit treaty or war while a unit is en route and confirm it stops at the last legal waypoint. For an invasion, remove the escort or introduce a hostile fleet before arrival and verify the landing is blocked without transferring control.
