# Implementation Evidence: Covert Operations and Counterintelligence

## Performance gate SC-007

The controlled benchmark in `tests/test_covert_operations_performance.py` uses 5,000 covert-cell records, including 1,000 cells preparing the 1,000 pending missions, plus two countries. It performs one warm-up update followed by five measured updates with `POLARS_MAX_THREADS=1`.

| Revision state | Change | Samples (ms) | Median | Gate |
|---|---|---:|---:|---|
| Before cell indexing | Original mission-to-cell linear lookups | 152.12, 137.16, 145.20, 144.40, 143.50 | 144.40 ms | Pass (<500 ms) |
| After iteration 1 | Build a cell-ID index once per update and use it for pending mission lookups | 44.80, 53.91, 46.40, 43.46, 47.28 | 46.40 ms | Pass (<500 ms) |
| Final targeted rerun | Same indexed implementation with discovery-visibility coverage enabled | 50.16, 46.12, 49.29, 42.84, 53.97 | 49.29 ms | Pass (<500 ms) |

The indexed lookup is behavior-preserving because cell IDs are the declared primary key. Covert lifecycle, AI action-path, mission visibility, and message-recipient tests pass alongside the benchmark. The system is about 66% faster than the pre-index baseline in this fixture; no unresolved SC-007 performance issue remains, and no further optimization iteration was needed.

## Verification

Run the functional checks with:

```powershell
$env:POLARS_MAX_THREADS = '1'
python -m pytest -q tests/test_covert_ai_policy.py tests/test_covert_operations_system.py tests/test_ai_policies.py tests/test_ai_integration.py
```

Run the opt-in performance gate with:

```powershell
$env:POLARS_MAX_THREADS = '1'
$env:RUN_COVERT_BENCHMARKS = '1'
python -m pytest -s -q tests/test_covert_operations_performance.py
```

## Final verification (2026-10-07)

The controlled runtime was Python 3.14.1, Polars 1.36.1, Windows 11 build 26200, 12 logical CPUs, and `POLARS_MAX_THREADS=1`. The isolated fixture contains 5,000 cells and 1,000 pending missions; after its warm-up, the latest five measured samples were 48.63, 61.59, 53.26, 50.57, and 55.42 ms (median 53.26 ms, max 61.59 ms). The <500 ms gate passed. This is a verification rerun of the indexed implementation, not another optimization iteration; the passing gate requires no further tuning and no performance issue is deferred.

The final focused functional run passed **48 tests and 14 subtests** across covert lifecycle/resolution, AI policy/action integration, military presentation, and GameState IPC. New checks cover cell capacity/funding rejection, duplicate mission rejection, eight distinct deterministic mission profiles, pending-mission continuation through snapshot and save/load, and the rule that transit cells do not add counterintelligence coverage.

Desktop acceptance criterion SC-005 (owner/target overview usability within 30 seconds) remains **unverified** because it requires live interactive-client acceptance. Headless tests do not establish that criterion; see open task T014.

## Update-local shared route preparation

Covert deployment and transit use the same `RegionRouteSnapshot` topology preparation and `RegionTravelTime` coordinate index as military movement. Both indexes are lazy and scoped to one `CovertOperationsSystem.update()`; route access, stationing, and segment decisions are still checked for each cell and refresh from the current map on the next update. The 2026-10-08 integrated 4,559-region scenario reduced covert-operations time on steps 2–3 from about 3.03 s to 0.27 s, with all table hashes and the canonical saved-state hash matching the baseline after three steps. This integrated result is separate from the isolated 5,000-cell SC-007 gate above and does not close the live overview usability task. See `docs/SIMULATION_OPTIMIZATION_REPORT.md`.
