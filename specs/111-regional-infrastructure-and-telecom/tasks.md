---
description: "Implementation tasks for regional infrastructure and telecommunications"
---

# Tasks: Regional Infrastructure and Telecommunications

**Input**: Design documents from `/specs/111-regional-infrastructure-and-telecom/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/infrastructure-actions.md](contracts/infrastructure-actions.md), and [quickstart.md](quickstart.md)

**Tests**: Required by the user's implementation request and SC-001–SC-007. Write focused policy/system/presenter tests before implementation and keep existing movement, budget, strategic, schema, and layer-boundary tests green.

**Organization**: One prioritized player story covers inspecting, investing in, maintaining, and recovering regional capacity. Foundational tasks establish schemas, actions, and migration compatibility; story tasks are ordered by data flow.

## Phase 1: Setup

**Purpose**: Establish deterministic fixtures and a reproducible validation baseline.

- [x] T001 [P] Add deterministic regional infrastructure fixtures for owned/unowned regions, category profiles, budgets, projects, and damage records in `tests/test_regional_infrastructure_fixtures.py`
- [x] T002 [P] Complete the runnable automated, save/load, interactive, and 100,000-record validation instructions in `specs/111-regional-infrastructure-and-telecom/quickstart.md`

---

## Phase 2: Foundational

**Purpose**: Establish typed, persisted data and semantic action contracts before simulation behavior.

- [x] T003 Add stable schemas and keys for `regional_infrastructure`, `infrastructure_projects`, and `infrastructure_damage_records` in `modules/base/schema.py`
- [x] T004 Add `ActionInvestRegionalInfrastructure` and `ActionCancelInfrastructureProject` payload contracts in `src/shared/actions.py` and document compatibility in `specs/111-regional-infrastructure-and-telecom/contracts/infrastructure-actions.md`
- [x] T005 Add deterministic legacy profile initialization that seeds from supported regional values or configured defaults without changing ownership, population, GDP, or treasury in `modules/base/systems/world/infrastructure_policy.py`
- [x] T006 Add schema/save-load/snapshot compatibility coverage for absent and partially populated infrastructure tables in `tests/test_schema_mod_migrations.py` and `tests/test_regional_infrastructure_system.py`

**Checkpoint**: New state is typed, additive, serializable, and safely initialized from existing worlds.

---

## Phase 3: User Story 1 — Invest in and maintain regional infrastructure (Priority: P1) 🎯 MVP

**Goal**: A player can inspect category condition/capacity, fund an authorized regional project, observe deterministic progress, and recover attributed damage without exceeding configured limits.

**Independent Test**: Run the policy/system/presenter tests, then verify a valid investment completes after game time, an invalid investment changes neither funds nor capacity, and a damaged category recovers only to its stored ceiling.

### Tests for User Story 1 (write first)

- [x] T007 [P] [US1] Test configured category bounds, quote calculation, maintenance/depreciation clamping, aggregation, and damage idempotency in `tests/test_infrastructure_policy.py`
- [x] T008 [P] [US1] Test legacy profile initialization, authority, insufficient funds, active-project conflict, atomic debit, pause/cancel/completion, deterministic game-time progress, and persisted damage in `tests/test_regional_infrastructure_system.py`
- [x] T009 [P] [US1] Test route, production/development, telecom, and strategic damage consumption of bounded regional outputs in `tests/test_infrastructure_integration.py`
- [x] T010 [P] [US1] Test read-only regional/national summary, project status, maintenance need, and recent source attribution in `tests/test_infrastructure_presenter.py`
- [x] T011 [P] [US1] Add a controlled 100,000-category-record / 1%-changed benchmark in `tests/test_infrastructure_performance.py`

### Implementation for User Story 1

- [x] T012 [US1] Implement category configuration, deterministic quotes, bounded capacity/aggregation, and source-idempotent damage/reconstruction policies in `modules/base/systems/world/infrastructure_policy.py`
- [x] T013 [US1] Implement authorized investment/cancellation, treasury reservation, project lifecycle, pause rules, depreciation, maintenance, and profile materialization in `modules/base/systems/world/infrastructure_system.py`
- [x] T014 [US1] Register the system and all action/table access contracts in `modules/base/registration.py` and `modules/base/systems/world/infrastructure_system.py`
- [x] T015 [US1] Connect regional transport and telecom coordination modifiers to existing route duration without replacing route legality in `modules/base/systems/military/military_system.py`
- [x] T016 [US1] Reconcile strategic/disaster impacts with source-attributed infrastructure damage and bounded reconstruction in `modules/base/systems/military/strategic_warfare_system.py` and `modules/base/systems/world/infrastructure_system.py`
- [x] T017 [US1] Feed national and regional capacity outputs into existing production/development/intelligence consumers in `modules/base/systems/economy/internal_economy_system.py`, `modules/base/systems/demographics/population_system.py`, and `modules/base/systems/military/covert_operations_system.py`
- [x] T018 [US1] Add AI investment decisions and budget-backed maintenance priorities through the existing declarative policy framework in `modules/base/systems/world/ai/infrastructure_policy.py` and `modules/base/systems/world/ai_system.py`
- [x] T019 [US1] Add a read-only infrastructure presenter and selected-region panel wired through the existing HUD/panel manager in `src/client/ui/panels/infrastructure_presenter.py`, `src/client/ui/panels/region_infrastructure_panel.py`, and `src/client/ui/components/hud/panel_manager.py`
- [x] T020 [US1] Verify accepted/rejected commands produce readable authorized status and reason records without client-side state mutation in `tests/test_layer_boundaries.py` and `tests/test_regional_infrastructure_system.py`

**Checkpoint**: A valid owned-region investment is visible, funded once, advances deterministically, and changes only the selected regional category and its declared consumers.

---

## Phase 4: Polish and cross-cutting validation

**Purpose**: Verify persistence, performance, and compatibility across existing gameplay domains.

- [x] T021 [P] Reconcile schema, baseline, damage-source, project-cancellation, and aggregation rules across `specs/111-regional-infrastructure-and-telecom/spec.md`, `data-model.md`, `contracts/infrastructure-actions.md`, and `quickstart.md`
- [x] T022 Run the feature quickstart and all focused plus movement, economy, strategic, save/load, migration, and layer-boundary regressions; record the actual results in `specs/111-regional-infrastructure-and-telecom/quickstart.md`
- [x] T023 Verify the 100,000-record incremental update target and report sample count, changed share, runtime, and environment in `tests/test_infrastructure_performance.py`

## Dependencies and execution order

- **Setup**: T001 and T002 are independent.
- **Foundational**: T003 and T004 establish schemas/actions; T005 depends on T003; T006 verifies compatibility after the contracts exist.
- **User Story 1**: T007–T011 are written first. T012–T014 establish and register the system. T015–T018 integrate the generated outputs into existing consumers. T019 adds read-only UI; T020 verifies command and layer behavior.
- **Polish**: T021–T023 require the story and integrations to be complete.

## Parallel opportunities

- T001/T002 can proceed independently.
- After the foundational contracts exist, T007, T009, T010, and T011 can be developed in separate test files.
- T015–T019 can proceed independently after the authoritative profile/materialization contract is stable, with shared-file coordination for `registration.py` and the named consumers.

## Implementation strategy

1. Establish the typed tables, action contracts, and deterministic fixtures.
2. Write failing policy, project lifecycle, compatibility, integration, and presenter tests.
3. Implement authoritative policy and system behavior, then connect current consumers.
4. Add the read-only client projection and AI policy.
5. Run the full validation flow and retain empirical results; do not infer the 1-second benchmark from unit-test completion.

## Scope guardrails

- Do not duplicate population, GDP, production, budget, ownership, or intelligence ledgers.
- Do not change region ownership or create output/population solely from infrastructure capacity.
- Do not let the client mutate `GameState` or decide construction costs, duration, damage, or refunds.
- Do not recompute all region pairs or all projects every simulation tick.
