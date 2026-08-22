---

description: "Dependency-ordered implementation tasks for Tactical Combat Resolution MVP"
---

# Tasks: Tactical Combat Resolution MVP

**Input**: Design documents from `specs/101-tactical-combat-resolution/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Organization**: Tasks are grouped by user story. All task lines use the required checklist format: `- [X] [TaskID] [P?] [Story?] Description with file path`; unchecked work uses `[ ]` until verified.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the passive contracts, schemas, and reusable fixtures that the feature phases build on.

- [X] T001 [P] Add the `ActionSetUnitReadiness` passive action and readiness target validation fields in `src/shared/actions.py` while preserving existing movement and attack action signatures.
- [X] T002 [P] Add passive readiness, battle lifecycle, and participant-rejection event dataclasses, including additive defaults for existing consumers, in `src/shared/events.py`.
- [X] T003 [P] Register additive unit, transition, pending-order, battle, participant, and occupation schemas plus keyed-table metadata in `modules/base/schema.py`.
- [X] T004 [P] Add server-owned legacy table/default migration and snapshot compatibility validation in `src/server/state_migrations.py` without adding gameplay logic to the shared snapshot codec.
- [X] T005 [P] Create deterministic headless state builders for units, wars, treaties, regions, and time advancement in `tests/test_tactical_combat_fixtures.py`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Provide shared military policies, system ordering, and persistence behavior before any user story is implemented.

**Checkpoint**: The foundation must be complete before user-story work begins.

- [X] T006 [P] Implement `ReadinessPolicy` with canonical lowercase statuses, 2/0/2/0-day transition durations, two ordered two-day parked-to-fortified stages, pause-safe progress math, and 0.25/1.0/1.5 contribution weights in `modules/base/systems/military/readiness_policy.py`.
- [X] T007 [P] Implement the treaty/war eligibility resolver interface for two sides, military allies, neutral countries, and ambiguous assignments in `modules/base/systems/military/alliance_policy.py`.
- [X] T008 Create the `ReadinessSystem` system shell with declared table access, action handling, dependency metadata, and deterministic update boundaries in `modules/base/systems/military/readiness_system.py`.
- [X] T009 Integrate `ReadinessSystem` before movement/combat through the military system façade and include new schemas in the base module contribution.
- [X] T010 Add additive defaults, invalid-status normalization, active-transition invariants, and pending-order persistence validation to `src/server/state_migrations.py`.
- [X] T011 [P] Add snapshot round-trip coverage for tactical readiness and battle tables in `tests/test_client_snapshot_performance.py` and the existing snapshot protocol.

---

## Phase 3: User Story 1 - Manage Unit Readiness (Priority: P1) 🎯 MVP

**Goal**: Let commanders request parked, ready, and fortified postures with authoritative timed progress, ETA, and visible status.

**Independent Test**: Create a newly deployed parked unit, execute every supported transition including the two-stage parked-to-fortified path, pause/save/load the simulation, and verify status, progress, ETA, and completion events.

### Tests for User Story 1

- [X] T012 [P] [US1] Add unit-readiness contract tests for lowercase defaults, idempotent requests, 2/0/2/0-day boundaries, progress clamping, pause behavior, absolute ETA derivation, and completion events in `tests/test_unit_readiness.py`.
- [X] T013 [P] [US1] Add persistence and deterministic replay tests for interrupted and reloaded readiness transitions in `tests/test_unit_readiness.py`.

### Implementation for User Story 1

- [X] T014 [US1] Extend unit creation and legacy-unit normalization so newly deployed units start `parked` while older saves receive a compatibility `ready` default in `modules/base/systems/military/military_system.py` (FR-001).
- [X] T015 [US1] Implement readiness command validation, transition-row creation, repeated-request idempotency, and target replacement behavior in `modules/base/systems/military/readiness_system.py`.
- [X] T016 [US1] Implement the readiness update loop that derives progress from the persisted absolute ETA, completes due transitions, advances the second fortified stage, persists pending-order references, derives remaining minutes without a second countdown, and emits readiness events in `modules/base/systems/military/readiness_system.py`.
- [X] T017 [US1] Add readiness columns and transition/pending-order frame normalization to the military system's unit table handling in `modules/base/systems/military/military_system.py`.
- [X] T018 [P] [US1] Extend `MilitaryPresenter.unit_rows` and its view model to expose stable status and readiness progress in `src/client/ui/panels/military/presenter.py`.
- [X] T019 [P] [US1] Render readiness labels and determinate progress bars in `src/client/ui/panels/military/unit_list_panel.py`.
- [X] T020 [P] [US1] Render current/target readiness, ETA, and progress in the selected-unit details view in `src/client/ui/panels/unit_details_window.py`.
- [X] T021 [P] [US1] Extend unit projection signatures and draw readiness progress overlays for selected and hovered units in `src/client/renderers/unit_renderer.py`.
- [X] T022 [US1] Add readiness commands to the unit interaction and context-menu flows in `src/client/controllers/unit_interaction_controller.py` and `src/client/ui/components/hud/unit_context_menu.py`.
- [X] T023 [US1] Verify the readiness story independently with focused tests and preserve the existing 7-test combat/engagement baseline.

**Checkpoint**: A commander can prepare a unit, see authoritative progress, reload the game, and observe the completed status without opening raw state data.

---

## Phase 4: User Story 2 - Issue Orders Around Readiness (Priority: P1)

**Goal**: Ensure movement and attack orders respect readiness, queue when necessary, and cancel fortified posture or active transitions according to the contract.

**Independent Test**: Issue move and attack commands to parked, ready, fortified, and transitioning units and verify no order executes early, fortified release is immediate, and combat interruption uses the last completed status.

### Tests for User Story 2

- [X] T024 [US2] Add pending-order tests for parked movement/attack queuing, release after readiness, replacement/cancellation, and invalid-target rejection in `tests/test_order_readiness.py`.
- [X] T025 [US2] Add fortified-release and combat-interruption tests covering last-completed-status contribution in `tests/test_order_readiness.py`.

### Implementation for User Story 2

- [X] T026 [US2] Implement normalized pending move/attack order creation, one-order-per-unit replacement, release, cancellation, and replay-safe status updates in `modules/base/systems/military/military_system.py`.
- [X] T027 [US2] Gate movement and attack execution on readiness, including immediate fortified-to-ready release and post-transition order execution, in `modules/base/systems/military/military_system.py`.
- [X] T028 [US2] Cancel active readiness transitions and pending orders when hostile contact begins, while preserving the last stable readiness status for combat, in `modules/base/systems/military/combat_system.py`.
- [X] T029 [US2] Expose readiness command availability and progress through the unit interaction, context-menu, and details flows.
- [X] T030 [US2] Extend movement and engagement regression coverage for readiness-gated orders in focused tests.
- [X] T031 [US2] Run the independent order-gating scenario and verify deterministic pending-order state after pause/save/load using focused tests.

**Checkpoint**: No movement or attack bypasses readiness; queued commands are visible, deterministic, and released exactly once.

---

## Phase 5: User Story 3 - Resolve Two-Sided Battles With Allied Support (Priority: P1)

**Goal**: Resolve hostile contact as one battle with exactly two aggregate sides, multiple principal/allied countries, readiness-weighted strength, and deterministic lifecycle events.

**Independent Test**: Place primary belligerents, an eligible ally, and a neutral country in one region, run rounds, and verify side membership, weighted strength, event uniqueness, stalemate/draw handling, and conclusion.

### Tests for User Story 3

- [X] T032 [US3] Add alliance eligibility tests for principal members, direct active military/defensive allies, transitive exclusion, neutral countries, missing presence, and ambiguous dual eligibility in `tests/test_battle_allies.py` (FR-009, FR-010, SC-005).
- [X] T033 [US3] Add two-side participant, engagement-zone anchor, and deterministic ordering tests for multiple countries per side in `tests/test_battle_allies.py`.
- [X] T034 [US3] Add lifecycle event tests for one start, changed-row updates, zero-strength removal, draw, diagnostic rejection, and one conclusion event in `tests/test_battle_allies.py` (FR-012, FR-013, SC-004).

### Implementation for User Story 3

- [X] T035 [US3] Complete `AlliancePolicy` table parsing and deterministic side assignment using direct active military/defensive treaties, with no transitive alliance expansion, in `modules/base/systems/military/alliance_policy.py`.
- [X] T036 [US3] Extend `CombatSystem` contact grouping to create exactly one `(region_id, war_id)` battle with two sides, deterministic engagement-zone anchoring, and persisted participant roles in `modules/base/systems/military/combat_system.py` (FR-008, FR-009, FR-010).
- [X] T037 [US3] Add readiness-weighted unit contributions, participant aggregates, round counters, balance, cumulative losses, and stable sorting to `modules/base/systems/military/combat_system.py` (FR-011).
- [X] T038 [US3] Implement active lifecycle, zero-strength removal, deterministic draw transitions, and battle lifecycle event emission in `modules/base/systems/military/combat_system.py` (FR-012, FR-013, SC-004).
- [X] T039 [US3] Preserve existing positional/assault combat behavior while extending schemas and assertions for allies in focused combat tests.
- [X] T040 [US3] Run the two-sided allied battle scenario and compare canonical rows/events across focused tests.

**Checkpoint**: Coalition battles have exactly two sides, neutral units stay out, readiness changes combat contribution deterministically, and lifecycle events are not duplicated.

---

## Phase 6: User Story 4 - Monitor Battle Status (Priority: P1)

**Goal**: Present battle lifecycle, both sides, participants, ally roles, readiness distribution, balance, losses, round, and map feedback from authoritative snapshots.

**Independent Test**: Feed active, updated, stalemate, and concluded battle snapshots into the presenter/panels and verify values refresh once, focus the correct region, and tolerate legacy snapshots.

### Tests for User Story 4

- [X] T041 [US4] Add `BattleStatusView` projection tests for side membership, ally roles, readiness distribution, round, balance, losses, occupation fields, and legacy defaults in `tests/test_battle_status_interface.py` (FR-014, SC-006).
- [X] T042 [US4] Add snapshot projection coverage for battle/unit changes in `tests/test_battle_status_interface.py`.

### Implementation for User Story 4

- [X] T043 [US4] Implement read-only `BattleStatusView` and participant/readiness aggregation helpers in `src/client/ui/panels/military/presenter.py` (FR-014, SC-006).
- [X] T044 [US4] Render lifecycle status, both side country lists, participant roles, balance, strengths, losses, round, and occupation summary in `src/client/ui/panels/military/battle_overview_panel.py`.
- [X] T045 [US4] Add battle selection/focus behavior that centers the map on the battle region without mutating authoritative state in `src/client/ui/panels/military/battle_overview_panel.py`.
- [X] T046 [US4] Add readiness snapshot signatures and refresh triggers for unit overlays and presenters in `src/client/renderers/unit_renderer.py` and the military presenters (FR-015, FR-018).
- [X] T047 [US4] Render active/stalemate battle markers from authoritative battle/unit snapshots in the tactical map overlay.
- [X] T048 [US4] Run the battle status interface scenario with full and legacy snapshot fixtures through focused tests.

**Checkpoint**: Players can understand and focus every active/stalemate/concluded battle from the interface without inspecting raw tables or causing client-side simulation writes.

---

## Phase 7: User Story 5 - Establish Military Occupation (Priority: P2)

**Goal**: Preserve political ownership while recording military control, garrison/resistance data, and contested occupation after a battle victory.

**Independent Test**: Resolve a battle in a region owned by the defeated side and verify controller transfer, owner preservation, occupation creation, garrison/resistance fields, and contested behavior.

### Tests for User Story 5

- [X] T049 [US5] Add occupation victory tests for controller transfer, owner preservation, garrison strength, fixed `resistance=0.0`, start time, and save/load persistence in `tests/test_occupation_resolution.py`.
- [X] T050 [US5] Add draw, no-garrison, and renewed-hostile-contact contested occupation tests in `tests/test_occupation_resolution.py`.

### Implementation for User Story 5

- [X] T051 [US5] Implement occupation row creation/update, controller synchronization, garrison calculation, resistance default, and contested-state transitions in `modules/base/systems/military/occupation_system.py` and the combat persistence path.
- [X] T052 [US5] Integrate winning-side and draw outcomes with occupation updates while preserving `regions.owner` in `modules/base/systems/military/combat_system.py`.
- [X] T053 [US5] Keep occupation processing in the combat/post-process persistence path with a standalone `OccupationSystem` contract available for server composition.
- [X] T054 [US5] Display occupation controller, owner, garrison, resistance, start time, and contested status in `src/client/ui/panels/region_inspector.py`.
- [X] T055 [US5] Run the occupation scenario and verify the region/control snapshot updates within one state update using focused tests.

**Checkpoint**: Tactical victory creates military occupation without silently annexing the region or losing contested state.

---

## Phase 8: Polish & Cross-Cutting Verification

**Purpose**: Validate determinism, performance, compatibility, architecture boundaries, and the complete quickstart before implementation handoff.

- [X] T056 [P] Add the large-single-battle scaling smoke fixture (1000 units) and bounded update-time assertion in `tests/test_tactical_combat_performance.py`; the separate 100-engagement gate is T074.
- [X] T057 [P] Add deterministic replay comparison helpers for canonical Polars rows and ordered domain events in `tests/test_tactical_combat_fixtures.py` (SC-001).
- [X] T058 [P] Audit new military code comments for English-only rationale and self-documenting names in the feature-owned military files.
- [X] T059 Run focused readiness, order, allied-battle, battle-status, occupation, and snapshot tests from `specs/101-tactical-combat-resolution/quickstart.md`.
- [X] T060 Run the complete `unittest` discovery suite and the existing combat/engagement regression command; the feature suite passes, while the full discovery run has two reproducible headless-server `multiprocessing` failures (`WinError 5` from the environment before server startup), recorded in the verification handoff.
- [X] T061 Run the quickstart scenarios through the deterministic headless fixtures and focused test command; all feature scenarios pass.
- [X] T062 [P] Add bounded headless snapshot codec round-trip coverage independent of graphics and network I/O in `tests/test_client_snapshot_performance.py`; the client update-loop budget is verified by T074.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001–T005 can begin immediately; T003 must finish before table-consuming implementation.
- **Foundational (Phase 2)**: T006–T011 depend on the relevant Setup contracts; this phase blocks all user stories.
- **User Story 1 (Phase 3)**: T012–T023 depend on T006, T008, T009, and T010.
- **User Story 2 (Phase 4)**: T024–T031 depend on User Story 1 completion because order gating consumes readiness state and transitions.
- **User Story 3 (Phase 5)**: T032–T040 depend on the Foundation and User Story 1; T028/T029 behavior from User Story 2 must be available for combat interruption.
- **User Story 4 (Phase 6)**: T041–T048 depend on the battle row/event shape from User Story 3 and unit readiness projection from User Story 1.
- **User Story 5 (Phase 7)**: T049–T055 depend on User Story 3 conclusion outcomes; its UI can be developed in parallel with late User Story 4 rendering once the occupation projection is defined.
- **Polish (Phase 8)**: T056–T062 depend on all selected MVP stories and their focused tests.
- **Convergence architecture**: T063 must pass before T068 because it changes the engagement helper import boundary; T064–T067 depend on the completed readiness/order foundation.
- **Convergence battle slice**: T068–T070 depend on T063 and the completed US3/US5 implementation; T069 must pass before T071–T072.
- **Convergence presentation/persistence**: T071–T073 depend on the authoritative rows and lifecycle behavior from T064–T070.
- **Convergence release gates**: T074–T075 run last, after T063–T073, and block completion if any clarified performance or replay invariant fails.

### User Story Dependencies

```text
Foundation
   |
   v
US1 Manage Readiness
   |
   v
US2 Orders Around Readiness
   |
   v
US3 Two-Sided Allied Combat -----> US5 Occupation (P2)
   |
   v
US4 Battle Status Interface
```

US1 is the first independently demoable slice. US2 is required before combat interruption can be trusted. US3 and US4 together form the tactical combat resolution MVP; US5 extends the MVP with occupation consequences.

### Within Each User Story

- Contract and integration tests are written before implementation tasks in the same story where practical.
- Passive schemas/contracts precede system policy; policy precedes client projection.
- Core implementation precedes integration and quickstart verification.
- A story checkpoint must pass before its dependents start.

## Parallel Execution Examples

### Setup and foundation

```text
T001, T002, T003, T004, T005
T006, T007, T011
```

These tasks touch separate passive contracts, schema/policy files, or test fixtures. T008–T010 follow the contracts they consume.

### User Story 1

```text
T012 then T013
T018, T019, T020, T021
```

Readiness contract tests are sequential because they share `tests/test_unit_readiness.py`; the four client surfaces can then proceed in parallel after the server contract shape is agreed. T014–T017 remain ordered because they share unit/system state.

### User Story 2

```text
T024 then T025
```

The pending-order and interruption tests share `tests/test_order_readiness.py` and run sequentially. T026–T028 then implement the shared server path before T029 client feedback.

### User Story 3

```text
T032 then T033 then T034
```

The three battle test groups share `tests/test_battle_allies.py` and run sequentially. T035–T038 are ordered because side assignment feeds combat aggregation and lifecycle events.

### User Story 4 and User Story 5

```text
T041 then T042
T049 then T050
```

View tests and occupation tests each run sequentially within their shared files, while the two groups can proceed in parallel after authoritative row shapes exist. Presenter work (T043–T048) and occupation policy work (T051–T054) can proceed in parallel once User Story 3 conclusions are stable.

## Implementation Strategy

### MVP-first delivery

1. Complete Phase 1 and Phase 2 so contracts, schemas, persistence, and system ordering are stable.
2. Complete User Story 1 and validate timed readiness independently.
3. Complete User Story 2 and validate order gating/interruption.
4. Complete User Story 3 and User Story 4 as the tactical combat resolution core: deterministic two-sided coalition combat plus a usable status interface.
5. Complete User Story 5 for occupation consequences before declaring this feature MVP complete, then run Phase 8 verification.

### Incremental delivery

1. Ship the readiness vertical slice after T023 for early UI and timing feedback.
2. Add order gating after T031 without changing the action contract.
3. Add coalition combat after T040 while preserving existing combat regression tests.
4. Add battle monitoring after T048 so every combat state is observable.
5. Add occupation after T055; although prioritized P2, it remains part of the full feature release gate before T059–T062.

### Completion criteria

- All tasks T001–T075 are checked off only after their files and tests are verified.
- Every user story passes its independent test criteria.
- The feature test suite, 100-engagement smoke scenario, bounded client snapshot-consumption check, and deterministic replay gate pass without client blocking or swallowed failures; the two full-discovery headless-server failures are isolated to the environment's denied Windows multiprocessing pipe creation and do not reach application startup.

## Phase 9: Convergence

- [X] T063 CRITICAL Move engagement geometry mechanisms to `src/core/map/engagement_geometry.py` and wartime relationship policy to `modules/base/systems/military/war_policy.py`, update all imports/tests, and add an import-boundary regression guard while preserving passive shared contracts per Constitution 1.1 and plan: shared layer ownership
- [X] T064 Implement status-aware gating for parked movement and attack orders, creating the required transition to `ready` and preserving valid pending orders when invalid commands are rejected; cover the clarified latest-valid replacement and invalid-order preservation matrix per FR-005, SC-003, and US2/AC3
- [X] T065 Correct the 2/0/2/0 readiness timing contract, two-stage parked-to-fortified schedule, minute-zero progress calculation, absolute ETA/derived remaining-time model, transition-row progress persistence, lowercase status values, and staged pending-order identity per FR-002, FR-003, FR-004, SC-002, and US1/AC2–AC7
- [X] T066 Release `fortified` units to `ready` before movement or attack execution and preserve the required immediate-order behavior per FR-006 and US2/AC2
- [X] T067 Make validated hostile contact interrupt readiness before due-transition completion, including same-minute movement contact and invalid attack rejection ordering, per FR-007 and US2/AC5
- [X] T068 Implement engagement-zone battle grouping with deterministic lowest-positive-region and unit-ID anchoring while limiting first-round contribution to stationary units in the anchor region per FR-008, US3/AC1, and plan: deterministic contact grouping
- [X] T069 Complete battle lifecycle state and event handling for `ACTIVE`, `STALEMATE`, and `CONCLUDED`, including updates when participant or readiness state changes and draw semantics per FR-012, FR-013, US3/AC6, and the US4 lifecycle contract
- [X] T070 Persist or update the occupation record in the same victory/post-process update as controller transfer, using raw garrison strength and preserving draw and contested behavior per FR-016, SC-007, US5/AC1–AC2, and plan: occupation post-process
- [X] T071 Expose the actual readiness target, persisted absolute ETA, derived remaining minutes, and rounded day/hour estimate in unit details and map overlays while retaining authoritative snapshot-only rendering per FR-002, FR-015, US1/AC7, and US4/AC3
- [X] T072 Render readiness distributions and complete occupation details in the battle overview and region inspector, including resistance, start time, controller, owner, and contested state per FR-014, US4/AC1–AC2, and US5/AC2
- [X] T073 Strengthen tactical save/load validation with unit-to-transition references, valid statuses and targets, timing/progress invariants, and pending-order links per FR-017, T010, and plan: server-owned persistence compatibility
- [X] T074 Add a performance smoke scenario covering at least 100 simultaneous active engagements with a server resolution tick `≤250 ms`, headless client snapshot consumption `≤100 ms`, representative payload `≤2 MB`, and no graphics/network I/O dependency per SC-008 and FR-018, extending T056 and T062
- [X] T075 Add deterministic replay verification that compares canonical tactical tables and ordered domain events across repeated identical simulations per SC-001 and T057
