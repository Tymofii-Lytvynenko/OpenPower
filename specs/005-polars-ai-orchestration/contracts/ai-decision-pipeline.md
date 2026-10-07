# Contract: Declarative AI Decision Pipeline

## Input

- A single immutable `AITableContext` with the state tables and simulation clock for one policy evaluation.
- Registered policies implement `TabularAIPolicy`: unique `id`, `required_tables`, `cadence_days`, `build_candidates(context) -> pl.LazyFrame`, and `resolve_action(row)`.
- Formula policies use table-column expressions and preserve read-only state semantics.

## Output

- Missing-input policies are listed as skipped; valid policies contribute normalized candidate LazyFrames.
- Candidates are scope-filtered, finite-positive utility ranked, conflict-deduplicated, and quota-limited in deterministic order.
- The combined decision frame is materialized once; winning rows resolve to semantic game actions.
- `AISystem` appends these actions to `state.current_actions`; it never mutates tables.

## Formula contract

- Financial runway and tax trigger, and military TCO/benefit/ROI/build conditions, match `spec.md` exactly except the existing tax cap at 50%, which remains an additional safety bound.
- Positive/zero cash flow uses runway 999 and produces no survival-tax action.
- ROI zero/nonpositive, reserves less-than-or-equal-to TCO, or nonpositive net income yields no build candidate.

## Determinism and failure

- Candidate ranking ties use stable payload data; identical context and policies produce the same decisions/actions irrespective of candidate row order.
- Non-LazyFrame scorer output, duplicate policy ID, or malformed protocol raises a clear exception rather than silently producing actions.
- Missing optional columns use policy-defined defaults; missing required tables skip only that policy.
- The <2 ms acceptance benchmark must report country count, Python/Polars versions, hardware/platform, thread count, warm-up, and sample statistic.
