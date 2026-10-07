---

description: "Dependency-ordered implementation tasks for migration and border mobility"

---

# Tasks: Migration and Border Mobility

**Input**: Design documents from `/specs/107-migration-and-border-mobility/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, and `contracts/migration-contracts.md`.

**Organization**: This feature has one primary player goal. Tasks are grouped into independently verifiable acceptance clusters derived from the spec's scenarios; these clusters do not add new requirements.

## Phase 1: Foundational Contracts and Registration

**Purpose**: Create typed, backward-compatible state/action/event contracts and register the new module system.

- [X] T001 [P] Add schema compatibility tests for absent migration tables, defaults, stable keys, and preservation of region cohort columns in `tests/test_schema_mod_migrations.py`.
- [X] T002 [P] Add action/event serialization contract tests for migration policy and lifecycle records in `tests/test_migration_integration.py`.
- [X] T003 Add `migration_policies`, `migration_policy_transitions`, `migration_flows`, and `migration_signals` typed schemas and keys in `modules/base/schema.py`.
- [X] T004 Extend `ActionUpdateMigrationPolicy` with defaulted effective-time and control values; define durable migration domain events in `src/shared/actions.py` and `src/shared/events.py`.
- [X] T005 Register `MigrationSystem` and its new phase in `modules/base/registration.py` and `src/shared/system_interfaces.py` after the system implementation exists.
- [X] T006 [P] Add layer-boundary assertions that migration simulation stays in `modules/base` and presenters stay in `src/client` in `tests/test_layer_boundaries.py`.

**Checkpoint**: New migration state normalizes for old saves without changing authoritative population data.

## Phase 2: User Story 1 — Move population through valid routes (Priority: P1) 🎯 MVP

**Goal**: Create, complete, and inspect directional domestic/international flows while preserving age cohorts and total population.

**Independent Test**: Run a two-region route fixture; assert no cohort mutation while pending, exact equal-and-opposite integer cohort transfer at completion, and unchanged world population total.

### Tests first

- [X] T007 [P] [US1] Add route, attractiveness, capacity, deterministic cohort-allocation, rounding, and zero/empty-region cases in `tests/test_migration_policy.py`.
- [X] T008 [P] [US1] Add pending/completed/redirected/rejected/cancelled lifecycle, due ordering, source cap, destination reservations, and exact conservation cases in `tests/test_migration_system.py`.
- [X] T009 [P] [US1] Add compatibility tests proving natural births, deaths, and aging remain separate from movement in `tests/test_population_system.py`.

### Implementation

- [X] T010 [US1] Implement pure bounded route eligibility, attractiveness, capacity, and integer cohort-allocation rules in `modules/base/systems/demographics/migration_policy.py`.
- [X] T011 [US1] Implement deterministic pending-flow creation, due processing, atomic region cohort transfers, status/reason records, and endpoint-indexed dirty recalculation in `modules/base/systems/demographics/migration_system.py`.
- [X] T012 [US1] Register the migration phase/system with dependencies on `base.population`, `base.ai`, and `base.diplomacy` in `src/shared/system_interfaces.py` and `modules/base/registration.py`.
- [X] T013 [US1] Preserve migration fields and exact cohorts through the existing population update path; do not allow pending flows to be counted as residents in `modules/base/systems/demographics/population_system.py`.

**Checkpoint**: Domestic flows pass deterministic conservation tests and do not change birth/death/aging semantics.

## Phase 3: User Story 2 — Control entry, exit, and border eligibility (Priority: P1)

**Goal**: Make effective-dated policies, active border restrictions, authority, and explicit diplomatic movement effects govern all new flows and in-flight transitions.

**Independent Test**: Apply policy and treaty changes at known game minutes; assert each cross-border decision uses the correct effective state and returns a stable reason code.

### Tests first

- [X] T014 [P] [US2] Add policy default, authority, finite/range, enum, effective-minute, and omitted-field compatibility tests in `tests/test_migration_system.py`.
- [X] T015 [P] [US2] Add border closure, hostile relations, war, explicit mobility agreement, and explicit movement-sanction cases in `tests/test_migration_policy.py`.
- [X] T016 [P] [US2] Add bootstrap tests proving legacy `country_laws` rows remain untouched and each country receives one default policy in `tests/test_migration_integration.py`.

### Implementation

- [X] T017 [US2] Resolve `ActionUpdateMigrationPolicy` with authority validation, bounded controls, default retention, and stable effective times in `modules/base/systems/demographics/migration_system.py`.
- [X] T018 [US2] Seed only missing default migration policy rows while preserving existing law records in `modules/base/systems/world/bootstrap_system.py`.
- [X] T019 [US2] Enforce current owners, both-country entry/exit settings, explicit treaty mobility effects, relation/war rules, and movement-specific sanctions in `modules/base/systems/demographics/migration_policy.py`.
- [X] T020 [US2] Revalidate authorized pending flows at completion and apply the documented finish-or-cancel transition rule with inspectable reason codes in `modules/base/systems/demographics/migration_system.py`.

**Checkpoint**: No ineligible border flow changes population; previously authorized flows follow their explicit transition rule.

## Phase 4: User Story 3 — Reflect migration in politics, labor, and services (Priority: P1)

**Goal**: Publish one bounded, persistent signal window for political and economic consumers without double application.

**Independent Test**: Complete working-age/dependent flows and assert labor/service signals change once, politics consumes the window once, and economic health combines migration pressure with its existing model.

### Tests first

- [X] T021 [P] [US3] Add labor, service-capacity, political-threshold, and signal-consumer watermark tests in `tests/test_migration_integration.py` and the economic-health integration suite.
- [X] T022 [P] [US3] Add migration AI candidate/action tests asserting the same policy and route restrictions as human actions in `tests/test_migration_ai_policy.py`.

### Implementation

- [X] T023 [US3] Aggregate completed migration into durable per-country gross/net, labor, service, and political signal rows in `modules/base/systems/demographics/migration_system.py`.
- [X] T024 [US3] Consume each political signal window once on the existing politics cadence and apply bounded approval/stability/law pressure in `modules/base/systems/politics/politics_system.py`.
- [X] T025 [US3] Incorporate unconsumed migration labor/service signals with the existing economic-health migration-pressure model in `modules/base/systems/economy/economic_health_system.py`.
- [X] T026 [US3] Implement a deterministic cadence-based `MigrationPolicy` and register it in `modules/base/systems/world/ai/migration_policy.py` and `modules/base/systems/world/ai_system.py`.
- [X] T027 [US3] Add integration tests proving population-dependent labor, GDP-per-capita input, development pressure, and service load observe the completed regional cohorts in `tests/test_migration_integration.py`.

**Checkpoint**: Player and AI decisions share the same authorization rules; downstream signals are bounded, saved, and consumed at most once per window.

## Phase 5: User Story 4 — Inspect migration outcomes (Priority: P2)

**Goal**: Show active policy, net/gross flow, capacity pressure, recent trend, top routes, and flow reasons for the selected country/region.

**Independent Test**: Build a presenter summary from a fixed state fixture and verify it shows the correct policy, totals, routes, pending status, and reason without changing state.

### Tests first

- [X] T028 [P] [US4] Add read-only country and region presenter tests for totals, top routes, policy, capacity, trend, and reason labels in `tests/test_migration_presenter.py`.

### Implementation

- [X] T029 [US4] Implement typed, read-only migration summary projections from canonical policy/flow/signal/region tables in `src/client/ui/panels/migration_presenter.py`.
- [X] T030 [US4] Implement a passive migration panel that dispatches only `ActionUpdateMigrationPolicy` in `src/client/ui/panels/migration_panel.py`.
- [X] T031 [US4] Register the migration panel in `src/client/ui/layouts/game_panel_registry.py` and add panel-registry coverage in `tests/test_migration_presenter.py`.

**Checkpoint**: The selected region’s net migration and active policy are visible without inspecting raw state; the client remains passive.

## Phase 6: User Story 5 — Preserve state, replay, and scale (Priority: P1)

**Goal**: Make old/new save, snapshots, repeated replay, and controlled due-flow processing stable.

**Independent Test**: Round-trip a pending flow and a signal watermark, replay identical actions three times, then process a 10,000-flow fixture with only due rows eligible for resolution.

### Tests first

- [X] T032 [P] [US5] Add full GameState save/load, snapshot, legacy-empty migration tables, and replay assertions in `tests/test_migration_integration.py`.
- [X] T033 [P] [US5] Add opt-in deterministic 10,000-pending-flow benchmark and due-only scan assertion in `tests/test_migration_performance.py`.

### Implementation and final verification

- [X] T034 [US5] Fix schema, persistence, or replay integration issues found by the save/load and snapshot tests without synthesizing history in `src/server/state_migrations.py` and `modules/base/schema.py`.
- [X] T035 [US5] Optimize due-flow ordering and dirty-endpoint route updates until the controlled benchmark is below 250 ms in `modules/base/systems/demographics/migration_system.py`.
- [X] T036 [US5] Run the complete focused suite and full repository test suite; record actual commands/results in `specs/107-migration-and-border-mobility/quickstart.md`.
- [X] T037 [US5] Revisit blocked economic-health integration tasks T013, T021, and T033 in `specs/112-economic-health-and-debt-failure/tasks.md`; close only those empirically completed by migration outputs and tests. T013, T021, and T033 are complete and backed by the economic/migration integration suites.
- [X] T038 [US5] Audit all 17 functional requirements and seven success criteria against tests/code, update `specs/107-migration-and-border-mobility/checklists/requirements.md`, and document any remaining engine/data limitation rather than marking it complete. SC-006 is explicitly marked as awaiting interactive UI confirmation; SC-007 records the measured controlled result.

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 — foundation**: Required before any runtime story work.
- **Phase 2 — mobility lifecycle**: Depends on the data/action contracts in Phase 1.
- **Phase 3 — policy/border eligibility**: Builds on the route lifecycle in Phase 2 and its stored authorization metadata.
- **Phase 4 — downstream/AI effects**: Depends on completed flows and effective policy from Phases 2–3.
- **Phase 5 — user presentation**: Depends on canonical tables and reason codes from Phases 1–4.
- **Phase 6 — save/replay/performance**: Validates the integrated outcome from every prior phase; task T037 also closes cross-feature dependencies only after evidence exists.

### Within a phase

- Write each listed test before its implementation task and observe the expected failure first.
- Schema/action contracts precede systems; pure policy precedes orchestration; orchestration precedes downstream consumers and UI.
- Tests marked `[P]` target separate files and can be authored in parallel, but implementation is performed sequentially in this run.
- Do not mark a task complete until its output exists and its relevant test/verification command passes.

## Implementation Strategy

Deliver the conserved domestic-flow path first, then layer international policy, downstream effects, AI, and user visibility on the same lifecycle. Finish with persistence, replay, performance, and cross-feature validation. Multiplayer is outside this feature scope.
