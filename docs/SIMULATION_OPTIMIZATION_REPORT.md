# Three Simulation Optimization Iterations

Measurements were taken on 2026-10-08 with one scenario: energy_crisis, seed 42, player UKR, 199 countries, and 4,559 regions. Each run starts a fresh headless session and performs three tick(0.6) steps at speed 5 with actions from modules/energy_crisis/scenarios/policy_response.json.

The initial run already includes the earlier coordinate optimization for covert cells. Time was measured with perf_counter without a sampling profiler. World loading, hash calculation, and report writing were outside the measured steps.

| Run | Step 1 (s) | Step 2 (s) | Step 3 (s) | Total (s) |
|---|---:|---:|---:|---:|
| Initial | 7.18 | 11.56 | 11.02 | 29.77 |
| Iteration 1: AI | 5.89 | 10.26 | 9.74 | 25.89 |
| Iteration 2: routes | 3.84 | 6.68 | 6.27 | 16.80 |
| Iteration 3: history | 3.28 | 5.88 | 5.24 | 14.40 |

Total speedup was **2.07×**, reducing elapsed time by **51.6%**.

## Changes

1. **AI.** Build the relationship index lazily once per policy evaluation and reuse it for all scheduled countries. Preserve both directions of each relationship, duplicate-record weighting, and deterministic target selection. On steps 2–3, AI time fell from 1.92–1.97 s to 0.59 s.
2. **Routes.** RegionRouteGraph separates topology preparation from path search. RegionRouteSnapshot lazily materializes regions, home-region indexes, and the graph for covert operations. Military orders reuse the prepared graph within one update. Access rules, movement costs, and unit capabilities are checked for each search. Indexes are not retained across system updates. On steps 2–3, covert operations fell from about 3.03 s to 0.27 s, while the military system fell from 1.43–1.47 s to 0.67–0.68 s.
3. **History.** Prepare record templates and stable fields once per update or indicator. Reuse the already-built series index. Determine compaction candidates with column operations before converting complete series records into Python dictionaries. On steps 2–3, history time fell from 2.50–2.62 s to 1.68–1.73 s.

## Verification

- After each iteration, hashes for every table and the canonical hash of the complete persisted state after three steps matched the initial run.
- **70 tests and 11 subtests** passed, covering transit, manual routes, access changes, equal-cost paths, map changes, duplicate relationship records, missing history data, compaction, and save/load.
- The existing covert-operations benchmark ran with 5,000 cells.
- git diff --check reported no formatting errors in the changed files.

Raw measurements and the comparison script were stored in a temporary local directory and were removed during repository cleanup. These are early-campaign measurements; longer campaigns and other scenarios were not measured in this comparison.
