# Implementation Plan: Economic Health and Debt Failure

**Branch**: `112-economic-health-and-debt-failure` | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/112-economic-health-and-debt-failure/spec.md`

## Summary

Add bounded economic-health indicators, effective-dated policy transitions, explicit debt contracts, scheduled debt service, arrears/restructuring/default lifecycles, and readable causes. Keep GDP, production, resource trade, and base budget calculations authoritative; extend the existing base economy and budget systems through typed Polars tables and semantic actions. New failure states constrain existing systems through bounded modifiers and never create unlimited funds or delete unrelated state.

## Technical Context

**Language/Version**: Python 3.14 in the current environment; code remains compatible with the repository's Python 3.10+ syntax baseline.

**Primary Dependencies**: Polars, existing `ISystem`/`SystemAccess`, `GameAction`, deterministic game time/events, base schema registry, Arrow snapshots, and generic save/load. No new runtime dependency.

**Storage**: Country-level indicators on `countries`; typed support tables for effective-dated policy transitions, foreign debt contracts, debt-distress cases, and attributable economic causes. Existing negative treasury reserves remain the domestic overdraft ledger.

**Testing**: pytest policy/system/action tests, existing economy/budget/trade/diplomacy/population/AI/save-load/layer-boundary regressions, deterministic replay checks, and an opt-in scheduled-debt scale benchmark.

**Target Platform**: Existing desktop client and authoritative headless simulation.

**Project Type**: Python modular simulation engine and desktop client.

**Performance Goals**: Process only due policy/debt transitions and countries whose indicators or obligations changed. The 10,000-country / 100,000-contract controlled benchmark must process scheduled obligations within one second when only a bounded due subset matures.

**Constraints**: Existing nominal GDP, resource trade, treasury, taxes, and budget allocations remain authoritative. Never fabricate reserves to cover debt service. Economic penalties are bounded; failure effects use existing budget, trade, migration, politics, diplomacy, health, and production contracts. Preserve deterministic replay, generic persistence, and passive-client/layer boundaries.

**Scale/Scope**: Country-level economic-health profiles, effective-dated policy transitions, and deterministic domestic/foreign loan contracts; this feature does not replace the resource market or implement real-world creditor institutions.

## Constitution Check

| Principle/gate | Result | Evidence/decision |
|---|---|---|
| Strict layer separation and passive client | Pass | Gameplay stays in `modules/base`; shared files contain data contracts only; UI presenters read snapshots and dispatch actions. |
| Data-oriented schemas and Arrow compatibility | Pass | New country attributes and keyed support tables use the base Polars schema registry and generic IPC/save paths. |
| Modular, reusable, SOLID design | Pass | Pure bounded policy calculations are separated from system orchestration, existing budget/economy integration, AI decisions, and client views. |
| Professional comments and maintainability | Pass | Self-documenting policy names; comments are reserved for causal rationale and non-obvious compatibility decisions. |
| Empirical verification and anti-masking | Pass | Tests cover treasury conservation, debt schedule arithmetic, transition timing, distress/recovery, deterministic replay, and benchmark behavior without fallback funds. |

No constitutional violation or complexity exception is required.

## Design Decisions

### Phase 0 — repository research

See [research.md](research.md). The existing `BudgetSystem` computes revenue, expenditure, negative-reserve interest, and reserve changes on real-second events; `InternalEconomySystem` computes national output and demand; country state already includes `economic_health`; AI budget logic already adjusts national allocations. None of these systems owns explicit contractual debt schedules, effective-dated wage/interest policy, inflation, labor outcomes, or distress state. New behavior extends those boundaries and keeps the existing market and GDP ledger intact.

### Phase 1 — typed state, actions, and compatibility

1. Extend the country runtime schema with bounded wage, rate, inflation, labor, poverty, real-income, and debt-summary indicators while preserving extra scenario columns.
2. Add keyed support schemas for effective-dated policy transitions, foreign debt contracts, distress cases, and cause records. Missing/partial legacy tables receive deterministic typed defaults without changing reserves or nominal GDP.
3. Add semantic actions for effective-dated policy changes, foreign borrowing from an existing creditor, and restructuring requests. Server policy owns authorization, bounds, cost, and eligibility.
4. Keep actions and events as passive shared data. Register economic-health policy in the base module and declare precise table/action access.

### Phase 2 — economic indicators and policy transitions

1. Derive baseline health, labor, inflation, and real-income values from existing GDP, reserves, budget, production, population, trade, and poverty inputs with explicit neutral defaults.
2. Accept only finite bounded policy proposals with authority and cooldown checks. Store effective times and apply them on deterministic game-time boundaries; do not rewrite prior values or history.
3. Update employment, wages, poverty, inflation, and economic health through bounded, inspectable component formulas. Record cause IDs and changes instead of silently mutating nominal ledger values.
4. Integrate inflation purchasing-power modifiers at existing demand/revenue boundaries and publish unemployment/poverty/economic-health modifiers to existing consumers without duplicating their ledgers.

### Phase 3 — debt service and distress lifecycle

1. Represent each foreign obligation as a typed contract with creditor, currency basis, principal, rate, maturity, next due time, schedule, conditions, status, and cumulative arrears. Continue exposing negative treasury reserves as domestic overdraft exposure.
2. Borrowing requires an existing creditor, authorized debtor, bounded terms, and explicit principal transfer; no lender or treasury funds are invented.
3. Include contractual interest and scheduled principal in budget capacity. At each due boundary, pay only from available funds; shortfalls create arrears and distress candidates.
4. Transition deterministically through current, arrears, restructuring, default, recovery-pending, and closed states. Apply bounded budget/trade/policy penalties, make second active rescue/default requests idempotently reject or merge, and clear only the restrictions whose recovery conditions are met.
5. Use the same command validation and lifecycle for AI actors; debt/cause/policy tables persist via the base schema registry.

### Phase 4 — read-only client and verification

1. Add an immutable economy presenter and selected-country debt/health panel showing current values, direction, thresholds, top recorded causes, policy timers, creditor obligations, next payment, and recovery conditions.
2. Add focused tests before each policy/system integration; keep existing budget/economy/trade/diplomacy/population/AI/save-load/layer tests green.
3. Run the quickstart, record measured results, inspect dirty changed country/contracts, and run the opt-in due-obligation benchmark. Visual scenarios are documented separately if no client UI can be launched in headless validation.

## Project Structure

```text
specs/112-economic-health-and-debt-failure/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/economic-actions.md
└── tasks.md

modules/base/
├── registration.py
├── schema.py
└── systems/economy/
    ├── budget_system.py
    ├── internal_economy_system.py
    ├── economic_health_policy.py
    └── economic_health_system.py

src/shared/
├── actions.py
└── events.py

src/client/ui/panels/
├── economy_presenter.py
└── economic_health_panel.py

tests/
├── test_economic_health_policy.py
├── test_economic_health_system.py
├── test_economic_health_integration.py
└── test_economic_health_performance.py
```

**Structure Decision**: Extend the existing base module/ECS organization. Shared actions/events contain only payloads; the base economy module owns gameplay policy; schemas own typed persisted state; the client presents immutable snapshot-derived models.

## Complexity Tracking

No constitutional violations. Debt contracts and distress cases are separate keyed entities because repayment obligations and national failure lifecycle have different ownership, schedules, and transition rules.
