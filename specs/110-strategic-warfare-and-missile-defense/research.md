# Strategic Warfare Implementation Research

## SC-007 Performance Gate

The opt-in benchmark in `tests/test_strategic_warfare_performance.py` resolves 1,000 due strikes against one unchanged region and evaluates two researched, operational defense layers per strike. It checks 1,000 resolved orders and exactly 2,000 defense results, with a 500 ms limit.

| Stage | Change | Measured duration | Gate |
| --- | --- | ---: | --- |
| Baseline, 2026-10-07 | No performance-specific changes; one controlled run | 3,616.11 ms | Fail |
| Iteration 1, 2026-10-07 | Added update-scoped region, research-level, and home-region indexes to avoid rebuilding lookups for each layer and strike | 3,867.99 ms (single run) | Fail; no improvement observed |
| Iteration 2, 2026-10-07 | Buffered strategic notifications and relation deltas, then wrote each table once after the strike batch | 140.49 ms | Pass |
| Iteration 3, 2026-10-07 | Avoided building strike indexes and notification buffers when there are no launch actions, due orders, or maintainable defenses | 126.91 ms | Pass |

SC-007 is met within the three-iteration limit. After the later readiness-impact and target-object behavior was added, a regression rerun measured 130.21 ms and again verified 1,000 impacts, 2,000 layer evaluations, 2,000 notifications, and bounded diplomatic relation effects. No further optimization iterations are planned for this gate.

## Unmeasured Workload Risk

- **PERF-110-01 — large concurrent production queue**: The research-gated production path now checks pending/readying production orders on simulation updates. The SC-007 fixture does not combine a large production queue with the 1,000-strike workload, so this mixed workload has not been measured. No optimization attempt has been made; avoid speculative tuning and profile this path only if a representative scenario reports a regression. The existing three-iteration SC-007 optimization budget remains closed.
