# Tasks: Economic Health and Debt Failure

**Input**: Design documents from `/specs/112-economic-health-and-debt-failure/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/economic-actions.md`, `quickstart.md`

**Tests**: Required by the user; add focused tests before each corresponding implementation and demonstrate failure before the fix.

## Phase 1: Foundational Contracts

**Purpose**: Establish persisted schema, semantic commands/events, registration, and migration safety before scenario behavior.

- [X] T001 [P] Add schema normalization/migration tests for economic indicators and support tables in `tests/test_schema_mod_migrations.py`.
- [X] T002 [P] Add action and domain-event serialization contract tests for economic policy/debt commands in `tests/test_economic_health_policy.py` and verify event journaling in `tests/test_economic_health_integration.py`.
- [X] T003 [US1] Add bounded country indicator defaults and typed policy/debt/distress/cause support tables in `modules/base/schema.py`.
- [X] T004 [US1] Add economic policy, debt request/decision/restructuring action dataclasses and readable transition events in `src/shared/actions.py` and `src/shared/events.py`.
- [X] T005 [US1] Register economic health/debt system in `modules/base/registration.py` with exact declared table/action access.
- [X] T006 [US1] Verify legacy seed, snapshot synchronization, and generic save/load round-trip for every new table in `tests/test_schema_mod_migrations.py` and `tests/test_economic_health_integration.py`.

## Phase 2: User Story 1 — Inspect and Change Economic Policy (P1)

**Goal**: Provide bounded, effective-dated wage/rate policy and stable country-level economic-health, labor, inflation, poverty, and purchasing-power indicators.

**Independent Test**: Submit valid and invalid policy commands, advance through and stop before effective boundaries, and verify deterministic indicators, causes, action results, and unchanged GDP/treasury when no configured fiscal effect applies.

### Tests

- [X] T007 [P] [US1] Test policy bounds, authority, cooldown, transition costs, effective minute, and invalid-action no-op in `tests/test_economic_health_integration.py`.
- [X] T008 [P] [US1] Test bounded indicator formulas, missing-source handling, inflation causes, real-income effects, labor supply/employment/unemployment/underemployment, and poverty feedback in `tests/test_economic_health_policy.py` and `tests/test_economic_health_integration.py`.
- [X] T009 [US1] Test deterministic policy application and component cause records across repeated seeded runs in `tests/test_economic_health_integration.py`.

### Implementation

- [X] T010 [US1] Implement pure scenario-bounded health, inflation, labor, wage, poverty, and real-income calculations in `modules/base/systems/economy/economic_health_policy.py`.
- [X] T011 [US1] Implement semantic policy validation, authorization, cost/cooldown rules, persisted effective transitions, and readable command results in `modules/base/systems/economy/economic_health_system.py`.
- [X] T012 [US1] Apply due policy transitions and update only affected country profiles; append attributable cause records and domain events in `modules/base/systems/economy/economic_health_system.py`.
- [X] T013 [US1] Integrate bounded inflation purchasing-power, wage/employment, health, and approval effects in current consumers; materialize the bounded migration-pressure output for the separate mobility consumer tracked by T033.

## Phase 3: User Story 2 — Contractual Debt and Recovery (P1)

**Goal**: Track domestic/foreign obligations, perform scheduled debt service without creating funds, and support arrears, restructuring, default, and bounded recovery.

**Independent Test**: Approve/reject a financing request, verify exact treasury conservation, advance to due dates with sufficient and insufficient funds, and exercise idempotent arrears, restructuring, default, and recovery transitions across save/load.

### Tests

- [X] T014 [P] [US2] Test request/creditor-approval authorization, lender-capacity checks, principal transfer, terms, rejection, and duplicate command idempotency in `tests/test_economic_health_system.py`.
- [X] T015 [P] [US2] Test scheduled interest/principal, partial payment, arrears, creditor transfer, maturity, and non-due no-op behavior in `tests/test_economic_health_system.py`.
- [X] T016 [P] [US2] Test restructuring/default/recovery thresholds, bounded restrictions, readable events, and no implicit forgiveness or fund creation in `tests/test_economic_health_system.py`.
- [X] T017 [US2] Test persistent debt schedules, distress timers, cause history, and next due outcome after snapshot/save-load in `tests/test_economic_health_integration.py`.

### Implementation

- [X] T018 [US2] Implement deterministic debt quote, schedule, due-service, arrears, distress, and recovery calculations in `modules/base/systems/economy/economic_health_policy.py` and `modules/base/systems/economy/economic_health_system.py`.
- [X] T019 [US2] Validate domestic/foreign contracts, creditor authority/capacity, principal transfer, and restructuring requests in `modules/base/systems/economy/economic_health_system.py`.
- [X] T020 [US2] Process due obligations only, settle bounded amounts between recorded parties, and materialize debt-service/balance summaries without rescanning unaffected contracts in `modules/base/systems/economy/economic_health_system.py`.
- [X] T021 [US2] Apply/remit bounded distress modifiers through current budget, trade, production, creditor/diplomacy, politics, and health integration points without deleting unrelated state; complete migration-flow consequences with T033.
- [X] T022 [US2] Integrate contractual service and bounded arrears/overdraft reporting with existing budget capacity while preserving the authoritative annual budget ledger in `modules/base/systems/economy/budget_system.py`.

## Phase 4: User Story 3 — AI, Events, and Economic Overview (P2)

**Goal**: Keep AI on the same validation path, expose current risks and obligations in a passive client view, and preserve deterministic observable transitions.

**Independent Test**: Run an AI country through the same accepted/rejected commands as a player, then inspect the immutable presenter output and verify UI actions contain commands only.

### Tests

- [X] T023 [P] [US3] Test AI policy/debt choices use semantic actions and the same server validation in `tests/test_economic_health_ai_policy.py`.
- [X] T024 [P] [US3] Test immutable presenter values, threshold/direction/cause ordering, creditor schedule visibility, and passive client-layer boundaries in `tests/test_economic_health_presenter.py` and `tests/test_layer_boundaries.py`.
- [X] T025 [US3] Test domain-event payloads and deterministic transition ordering in `tests/test_economic_health_integration.py`.

### Implementation

- [X] T026 [US3] Add declarative AI economic-health/debt policy and register it using existing AI context and action validation in `modules/base/systems/world/ai/` and `modules/base/systems/world/ai_system.py`.
- [X] T027 [US3] Add immutable snapshot-derived economy/debt presenter for selected-country values, trend, thresholds, obligations, causes, and recovery conditions in `src/client/ui/panels/economy_presenter.py`.
- [X] T028 [US3] Add selected-country economic-health/debt overview panel using presenter data and semantic actions only in `src/client/ui/panels/economic_health_panel.py` and the existing panel registry/view wiring.

## Phase 5: Performance, Documentation, and Regression

**Purpose**: Verify incremental due-work behavior and preserve existing systems.

- [X] T029 [P] Add an opt-in reproducible 10,000-country / 100,000-contract due-obligation benchmark in `tests/test_economic_health_performance.py`.
- [X] T030 [US2] Optimize and verify due-time filtering and changed-row updates against the one-second controlled target in `modules/base/systems/economy/economic_health_system.py`; latest 10k-country/100k-contract/100-due run: 0.060 seconds.
- [X] T031 [P] Update schema/action contracts, migration notes, and manual UI instructions to reflect implemented behavior in `specs/112-economic-health-and-debt-failure/data-model.md`, `contracts/economic-actions.md`, and `quickstart.md`.
- [X] T032 Run the focused and related economy, budget, trade, diplomacy, population-health, approval, AI, save/load, and layer-boundary tests; record exact evidence in `specs/112-economic-health-and-debt-failure/quickstart.md`.
- [X] T033 [US1/US2] Complete the migration-pressure consumer and verify economic migration feedback after the flow lifecycle in feature 107 exists; until then retain this signal as a read-only output and do not claim migration feedback is complete.

## Dependencies & Execution Order

- Phase 1 blocks all behavior work because the actions, persisted schemas, and migration behavior are shared foundations.
- User Story 1 precedes debt processing because debt distress and service use the economic profile and cause/event contracts.
- User Story 2 precedes AI and overview wiring so both consume stable, validated lifecycle state.
- Tests within a story are written before implementation; a test marked parallel is in a distinct test module and has no data-contract dependency on another test task.
- Final benchmark and regression evidence depends on all three user stories.
- T013, T021, and T033 are complete: migration signals are consumed by the economic-health profile, and bounded distress restrictions are applied through the existing budget, trade, production, creditor, politics, and health integration points. The focused economic/migration integration suites and full repository suite pass.
