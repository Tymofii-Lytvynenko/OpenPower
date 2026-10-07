# Tasks: Declarative Polars AI Orchestration

**Input**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/ai-decision-pipeline.md`

**Tests**: Required for formulas, lazy protocol, deterministic conflict resolution, actions, and opt-in performance.

## Phase 1: Reusable declarative framework

- [X] T001 [US1] Define immutable AI context, scorer protocol, normalized candidate schema, and missing-table handling in `src/core/ai_framework.py`.
- [X] T002 [US1] Combine policy LazyFrames and deterministically sort, deduplicate conflicts, apply quota/delegation filters, materialize once, and resolve actions in `src/core/ai_framework.py`.
- [X] T003 [P] [US1] Verify registration, lazy-frame enforcement, deterministic tie-breaks, cadence, delegated scopes, quotas, and missing-table handling in `tests/test_ai_framework.py`.

## Phase 2: Financial survival and military ROI

- [X] T004 [US2] Implement runway/tax survival scoring and budget action resolution in `modules/base/systems/world/ai/budget_policy.py`.
- [X] T005 [US3] Implement five-year TCO/protected-GDP ROI scoring with reserve and positive-income guards in `modules/base/systems/world/ai/military_policies.py`.
- [X] T006 [P] [US2] Cover tax trigger, discretionary budget changes, and cash-flow boundaries in `tests/test_budget_ai_policy.py`.
- [X] T007 [P] [US3] Cover exact ROI formula, no-build guardrails, and dispatch through `AISystem` in `tests/test_budget_ai_policy.py` and `tests/test_ai_system.py`.
- [X] T008 [US3] Prevent simultaneous immediate recruit and same-country queued procurement from `ProcurementPolicy` in `modules/base/systems/world/ai/military_policies.py`.

## Phase 3: Registration and performance acceptance

- [X] T009 Register independent economy, budget, military, diplomacy, politics, research, infrastructure, and migration policies through `AISystem` in `modules/base/systems/world/ai_system.py`.
- [X] T010 Pin the controlled 220-country scorer benchmark to one Polars thread before Python starts and assert the initialized pool size; latest scorer-only median is 1.53 ms.
- [X] T011 Measure the complete framework ranking/action path and record the measured gap in `tests/test_ai_performance.py`; latest median is 8.40 ms versus the 2.00 ms target.
- [X] T012 Run the full suite after the benchmark changes: `684 passed, 16 skipped, 116 warnings, 190 subtests passed in 162.89s`.

## Dependencies & Execution Order

- The generic protocol/resolver (T001–T003) is foundational for all scorer policies.
- Formula policies (T004–T008) are independent; registration (T009) wires them into daily simulation.
- T010–T011 are acceptance gates after formula and integration behavior is stable.
- The scorer-only SC-001 benchmark passes under the documented one-thread benchmark policy. T012's recorded full-suite regression passed (684 passed, 16 skipped, 116 warnings, and 190 subtests). The complete framework path remains a separate measured 6.40 ms-over-target follow-up if acceptance includes ranking and action resolution; see `research.md`.
