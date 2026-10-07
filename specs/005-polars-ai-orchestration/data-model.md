# Data Model: Declarative Polars AI

AI evaluation consumes immutable/read-only frames and produces a transient decision frame plus semantic actions; it adds no authoritative game-state tables.

## Context and decisions

| Structure | Fields | Contract |
|---|---|---|
| `AITableContext` | table snapshot mapping, day ordinal, simulation minute/date, player tag, globals, delegation domains/targets/treaties | Immutable context for a single evaluation pass. `table(name)` exposes LazyFrame view when present. |
| Candidate frame | `country_id`, `policy_id`, `domain`, `utility`, `conflict_key`, `action_kind`, `reason_code`, `quota`, policy payload | Each policy returns a Polars LazyFrame; framework normalizes required fields/types/defaults before joining. |
| Decision frame | candidate fields plus `rank` | Deterministically sorted, finite positive-utility winners after delegation scope, conflict de-duplication, and per-country/domain quota. |
| `AIEvaluation` | actions, decision DataFrame, skipped policy IDs | Immutable result; actions are resolved by the policy that created the candidate. |
| Country economic/military inputs | GDP, development, cash, annual revenue/expense, military count, threat perception, budget ratios | Read-only inputs for the financial survival and military ROI policies. |

## Financial formulas

- Annual net income = total annual revenue − total annual expense.
- If net income is negative, runway months = `max(money_reserves, 0) × 12 / max(abs(net_income), 1)`; otherwise runway is 999.
- If deficit runway is under 12 months (or reserves are already negative), emit survival utility `clip(1 − runway / 12, 0, 1)` and increase personal income tax by 0.02 up to 0.50 while reducing discretionary allocations.

## Military formulas

- 5-year unit TCO = `$1,000,000 + $500,000 × human_dev × 5`.
- 5-year protected GDP = `GDP × 0.01 × 0.85^military_count × trait_threat_perception`.
- ROI = `(benefit − TCO) / TCO`; build utility is clipped ROI only when ROI is positive, reserves exceed TCO, and annual net income is positive.
- `ProcurementPolicy` suppresses queueing a force-gap for a country when the immediate ROI scorer already proposes a build.

## Resolution invariants

- Every policy has a unique stable ID, declares required tables/cadence, returns LazyFrame candidates, and owns the resolver for its action kind.
- Null, non-finite, and non-positive utilities are filtered; duplicate country/conflict keys resolve to one deterministic winner; quotas cap winners per country/domain.
- Missing required input tables skip only affected policies and are reported in `skipped_policies`.
- Policies never mutate source tables; action execution occurs later through registered systems.
