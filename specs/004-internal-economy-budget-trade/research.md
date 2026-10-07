# Research: Internal Economy, Budget & Trade

## Decisions

### Keep Polars as the authoritative tabular boundary and retain aligned fast paths

- **Decision**: Inputs and outputs of simulation systems remain Polars DataFrames/LazyFrames with the established table schemas. Retain temporary NumPy buffers in the current aligned fast paths where they reduce work; keep policy-aware Polars/general fallbacks for irregular, treaty-constrained, regional, or effect-modified inputs.
- **Rationale**: The project constitution mandates Polars/Arrow for world datasets and the engine passes economic state through `GameState.tables`. A second authoritative state representation would add conversions and schema-consistency risks, while the existing aligned paths already exploit dense country/resource matrices.
- **Evidence**: The Polars documentation describes lazy plans as optimizable before execution and supports plan inspection with `LazyFrame.explain()`. `polars.collect_all` can share common upstream plans, but these are candidates only where work is genuinely shared. The current benchmark shows that indiscriminately converting materialized frames to LazyFrames is not enough: existing NumPy fast paths still take most of the tick time.
- **References**: [Polars lazy optimizations](https://docs.pola.rs/user-guide/lazy/optimizations/) and [Polars `collect_all`](https://docs.pola.rs/api/python/stable/reference/api/polars.collect_all.html).

### Preserve stable reductions and formula parity

- **Decision**: Keep stable-sum helpers and compare optimized outputs against the straightforward specification path with explicit tolerances and exact key/schema checks.
- **Rationale**: The budget and demand cycle repeatedly aggregates values; nondeterministic or reordered reductions can produce drift and violate SC-002 even if an individual tick looks numerically close.
- **Verification**: Tests cover zero supply/demand, missing optional columns, nulls, non-finite inputs, dependency ordering, treaty constraints, and repeated ticks. Performance runs use fixed deterministic fixtures and report warm-run distributions, not a single best sample.

### Retain policy-aware fallback behavior and reproducible monetary reductions

- **Decision**: Any optimized unconstrained-market path must detect whether regional production, treaty effects, unusual keys, or unsupported schemas require the existing general Polars path.
- **Rationale**: A speed path must not bypass bilateral allocation, affordability modifiers, tax behavior, stockpile physics, or schema compatibility.
- **Verification**: Differential tests run both paths on equivalent fixtures and assert ledger, country budgets, production, stockpiles, and trade-network outputs. Extend coverage with cancellation-prone values, permuted input rows, null/missing/non-finite fields, and values immediately around stockpile penalty thresholds before expanding fast-path eligibility.

## Performance profile and open question

`tests/test_economy_performance.py` defines a 220-country × 36-resource fixture (7,920 production rows), one warm-up pass, five sequential state-mutating measurements per system, and a sum of the three system medians. On Python 3.14.1 / Polars 1.36.1, with `POLARS_MAX_THREADS=1`, an earlier controlled run measured trade at 4.00 ms, economy at 4.95 ms, budget at 1.53 ms, and the combined gate at 10.48 ms. A consecutive run on that source revision measured 12.26 ms; an earlier run measured 9.36 ms, indicating material host/runtime timing variability. The demand calculator now reuses only its validated identifier layout and compiled formula plan, refreshing all dynamic values each tick; trade skips sorting only when key ordering proves the export/import concatenation is already canonical. Both optimizations retain general paths for changed/irregular keys, and deterministic `fsum` remains the fallback for negative/non-finite dense rows. SC-003 remains open and the <5 ms gate is not met.

An instrumented `cProfile` pass after the benchmark warm-up (same system order) identified these main cost centers; profiler wall times are diagnostic only and are not used as benchmark acceptance evidence:

| System | Dominant measured work | Profile evidence |
|---|---|---|
| Trade | Validation, numeric-array transforms, and output materialization | Exact key-series checks protect cached country/resource indices; the cache removes repeated Python mapping loops after the first stable layout. |
| Internal economy | Formulaic demand and resource-ledger construction | `_calculate_formulaic_consumption`, `_build_resource_ledger`, and `_process_economy` remain dominant; demand keys are emitted in canonical order to avoid sorting the full output matrix. |
| Budget | Deterministic dense demand reduction and fiscal output | The dense fast path reuses a verified country/resource layout and retains `stable_total` reductions; active modifiers and irregular tables stay on the existing general Polars path. |

A focused 30-sample median probe had earlier found dictionary mapping faster than NumPy object-array `searchsorted`; the retained design builds those mappings only after a layout change and reuses them after exact key-series equality checks. A separate unique-label-plus-inverse-index prototype was slower and was not retained. These local probes and the dense-budget parity check do not close the full-tick gate; the opt-in end-to-end benchmark remains authoritative.

A follow-up audit found that the market fast path cached row indices against the incoming production order, then sorted production for output. When the incoming resource order was not canonical, later ticks could not reuse those cached indices. The cache now stores keys and index vectors in the emitted canonical order; a regression compares the unsorted-input fast path with the policy-aware path and checks cache reuse after the next ledger is canonicalized. The next controlled full-tick run measured 9.43 ms (trade 3.59 ms, economy 4.53 ms, budget 1.31 ms). The cache correction is behavior-preserving but does not meet SC-003; the target remains open.

### Bounded optimization attempts and deferred performance issue

Per the implementation constraint, this pass allows at most three algorithm-optimization iterations before moving to other specification work. All three have been used, and SC-003 is still unmet:

| Attempt | Change and correctness guard | Controlled result |
|---|---|---|
| 1 | Corrected the market cache to index the canonical emitted order rather than the unsorted incoming order; added fast/general-path parity and cache-reuse coverage. | 9.43 ms combined (trade 3.59, economy 4.53, budget 1.31). |
| 2 | Cached country-to-population row alignment while refreshing population values on every tick; covered changed values, reordered population rows, missing population rows, and malformed values. | 9.45 ms combined (trade 3.72, economy 4.39, budget 1.34); no net improvement beyond measurement variance. |
| 3 | Moved eligible fast-path numeric validation onto the already extracted NumPy arrays, retaining the general Polars validation fallback for irregular inputs. An intermediate repeated-Polars-validation variant measured 14.63 ms and was replaced within this attempt. | Three same-revision runs: 8.44, 8.54, and 8.22 ms; latest breakdown 3.48 trade, 3.40 economy, 1.33 budget. |

Correctness/parity verification for the touched economy paths passes (40 focused tests at the time of measurement). The latest combined median sum remains above the required <5 ms threshold, so the performance gate is explicitly an open follow-up issue; do not spend another optimization iteration in this implementation pass. Resume in a dedicated performance pass, beginning with materialization/intermediate-ledger profiling on the same deterministic fixture, and retain the existing scheduler-order, policy, and monetary-reduction constraints.

Any future batching must preserve scheduler dependencies, each `EventRealSecond` iteration, and state transitions; do not fuse consecutive ticks or alter monetary reductions (`stable_sum` / `math.fsum`) without replay/parity evidence.

## Rejected alternatives

- **Replace state tables with NumPy arrays**: rejected because it conflicts with the project's Polars/Arrow data contract and would require broader conversions and schema ownership changes. Temporary aligned buffers in the current fast paths are not authoritative state.
- **Remove treaty/regional processing from the tick**: rejected because that changes gameplay behavior.
- **Relax the <5 ms target**: not authorized by the feature request; report measured results and preserve the gate.
