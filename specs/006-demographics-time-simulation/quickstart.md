# Quickstart: Demographics and Time Simulation

## Focused tests

```powershell
.venv\Scripts\python.exe -m pytest tests/test_population_system.py tests/test_time_system.py -q
```

The focused suite covers annual cohort equations, legacy defaults, paused heartbeat behavior, all speed levels, leap-day conversion, and long elapsed intervals.

## Controlled performance gate

```powershell
$env:RUN_POPULATION_BENCHMARKS = "1"
.venv\Scripts\python.exe -m pytest tests/test_population_performance.py -q -s -p no:cacheprovider
```

Record the runtime, Python/Polars version, thread count, region count, and median. SC-003 remains open unless the measured median is below 2 ms for 10,000 regions.

Validated on Python 3.14.1 / Polars 1.36.1 / 10,000 regions with the canonical schema registry enabled. The system reuses country-aligned parameters when its immutable region frame is unchanged and uses a NumPy vectorized cohort path for the standard numeric schema; replaced frames are checked for ID/owner changes and unsupported inputs retain the Polars fallback. Four consecutive default 12-thread runs measured **1.308 ms, 1.543 ms, 1.318 ms, and 1.297 ms** median after five warmups. The controlled one-thread median was **0.923 ms**. SC-003 passed in all five runs.

## Focused results

- `tests/test_population_system.py tests/test_time_system.py`: **9 passed**.
- The same focused tests plus the opt-in 10,000-region benchmark: **10 passed**.
- Latest complete repository suite after the demographic vectorization, identity-cache, and schema-normalization changes: **684 passed, 16 skipped, 116 warnings, 190 subtests passed in 162.89 seconds** (2026-10-07).

## Manual acceptance boundary

The automated tests establish headless clock and demographic behavior. Interactive speed-control and date display behavior require a client run and are not inferred from system tests.
