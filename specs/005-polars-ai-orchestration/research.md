# Research: Declarative Polars AI Orchestration

## Decisions

### Keep generic orchestration in core and concrete scorers in modules

- **Decision**: Preserve the actual split: `src/core/ai_framework.py` defines policy protocol, context, normalization, ranking, de-duplication, and action resolution; `modules/base/systems/world/ai/` implements economic, diplomatic, political, military, and other gameplay decisions.
- **Rationale**: The core framework is policy-agnostic and reusable, while concrete AI weights and actions are module gameplay rules. Moving it to engine is unnecessary and risks violating the constitution's layer boundaries.
- **Evidence**: `AISystem` creates `AITableContext`, registers policies, and appends resolved actions. Framework code requires LazyFrames and collects the combined candidate graph once.

### Keep financial survival and military ROI as composable policies

- **Decision**: Retain a separate `BudgetSurvivalPolicy` and `MilitaryROIPolicy`; express their formulas lazily, then register them with the framework.
- **Rationale**: A single registry lets new scorers join without edits to the resolver loop, while each policy owns its formula and action mapping.
- **Evidence**: `tests/test_budget_ai_policy.py` covers runway/tax and 5-year ROI behavior; `tests/test_ai_framework.py` covers lazy-frame protocol, deterministic ranking, quota, and conflicts.

### Define benchmark thread policy explicitly

- **Decision**: Pin the controlled 220-country benchmark to one Polars thread before process start; leave the production worker on Polars' automatic pool until whole-simulation profiling justifies an override.
- **Evidence**: On Python 3.14.1 / Windows 11 / Polars 1.36.1, the latest one-thread scorer-only median is 1.53 ms, below the 2 ms target. The complete framework path, including ranking, conflict resolution, and action objects, measured 8.40 ms. The earlier default 12-thread scorer-only median was 2.97 ms. The [official Polars thread-pool documentation](https://docs.pola.rs/api/python/stable/reference/api/polars.thread_pool_size.html) states the environment variable must be set before process start and recommends automatic sizing unless a specific context warrants overriding it.
- **Rationale**: The spec does not define thread count or hardware. The pinned setting makes the small scorer comparison repeatable, while keeping automatic sizing in production avoids trading away throughput in unrelated, larger simulation workloads based only on a narrow benchmark.

## Remaining acceptance evidence

- The scorer-only SC-001 gate passes at 1.53 ms. The complete framework path remains a separate open performance follow-up at 8.40 ms versus 2 ms if acceptance includes ranking and action resolution. No algorithm-optimization iteration has been spent on that broader path; first profile it in a dedicated pass, then cap any optimization work at three measured iterations and retain the current deterministic-resolution tests.
- Keep formula edge/boundary tests for bankruptcy runway 0/12 months, reserve thresholds, ROI exactly zero, and cash deficit.
