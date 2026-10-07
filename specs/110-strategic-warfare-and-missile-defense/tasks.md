# Tasks: Strategic Warfare and Missile Defense

**Input**: Design documents from this feature directory.

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/strategic-warfare.md`, and `quickstart.md`.

**Scope**: Multiplayer (`specs/102`) and game-editor-only requirements are excluded. The three-iteration performance allowance for SC-007 has already been used and the measured gate passes; do not perform additional optimization iterations for that gate.

## Phase 1: Setup and Shared Contracts

**Purpose**: Keep the domain schema, module registration, and documented scope aligned.

- [x] T001 Verify the strategic table schemas and `base.strategic_warfare` registration in `modules/base/schema.py` and `modules/base/registration.py`.
- [x] T002 Add per-weapon research/flight/production/readiness profile fields, launch-origin persistence, and durable production-order timing fields in `modules/base/schema.py`.

## Phase 2: User Story 1 - Research and Configure Strategic Assets (Priority: P1)

**Goal**: Strategic weapons and defenses remain gated by their completed research tracks, and scenario data can configure enabled weapon classes and timing.

**Independent Test**: A weapon cannot launch before both strategic-program and weapon research are complete; configured design payload caps and per-weapon timing are honored.

- [x] T003 [P] [US1] Add tests for program/weapon research gates, payload caps, scenario-configured production, readiness, and launch-origin validation in `tests/test_strategic_warfare_system.py`.
- [x] T004 [US1] Add the research-gated weapon production action/queue and scenario-profile bootstrap wiring in `src/shared/actions.py`, `modules/base/systems/military/strategic_warfare_system.py`, and `modules/base/systems/world/bootstrap_system.py`.

## Phase 3: User Story 2 - Validate and Launch a Strategic Strike (Priority: P1)

**Goal**: A valid action creates one pending order with its selected target, mode, payload, authorization, cost, and configured resolution time; invalid actions do not consume assets or funds.

**Independent Test**: Cover owner, target, range, readiness, authorization, research, duplicate order, object, payload, and cost rejection, plus per-weapon/global timing.

- [x] T005 [P] [US2] Add launch-time, origin, research-level, and non-mutation rejection cases to `tests/test_strategic_warfare_system.py`.
- [x] T006 [US2] Use positive weapon `flight_minutes` before `strategic_flight_minutes` and persist the resolved origin in `modules/base/systems/military/strategic_warfare_system.py`.
- [x] T007 [US2] Preserve player/AI action compatibility and document the authoritative launch contract in `src/shared/actions.py` and `specs/110-strategic-warfare-and-missile-defense/contracts/strategic-warfare.md`.

## Phase 4: User Story 3 - Resolve Layered Missile Defense (Priority: P1)

**Goal**: Only researched, operational, ready, covered layers attempt interception in configured order, with deterministic probability and no downstream impact after interception.

**Independent Test**: Verify exact attempt sequence, default and overridden probabilities, readiness consumption, coverage/range boundaries, and deterministic repeatability.

- [x] T008 [P] [US3] Complete layered-defense boundary tests in `tests/test_strategic_warfare_system.py`.
- [x] T009 [US3] Keep scenario defaults and configured payload/defense profiles aligned in `src/shared/strategic_profiles.py` and `modules/base/systems/military/strategic_warfare_system.py`.

## Phase 5: User Story 4 - Apply Bounded Military and Civilian Consequences (Priority: P1)

**Goal**: Surviving strikes create distinct, bounded intended and collateral effects through existing authoritative tables.

**Independent Test**: Military object targeting does not affect neighboring units; civilian effects stay bounded and reduce the authoritative country approval field.

- [x] T010 [P] [US4] Add a civilian-impact test asserting `gvt_approval` changes within `[0, 100]` in `tests/test_strategic_warfare_system.py`.
- [x] T011 [US4] Update country consequences to use `gvt_approval` with a legacy `approval_rating` fallback in `modules/base/systems/military/strategic_warfare_system.py`.
- [x] T012 [US4] Verify impact categories, collateral records, notifications, and relations remain auditable through existing system tests in `tests/test_strategic_warfare_system.py`.

## Phase 6: User Story 5 - Preserve Escalation and AI Policy (Priority: P2)

**Goal**: AI and player orders share authoritative validation, and detection/resolution only reveal details to authorized recipients.

**Independent Test**: Retaliation requires a confirmed impact; notifications and relation changes are deterministic and avoid revealing unresolved impact details.

- [x] T013 [P] [US5] Verify policy and visibility cases in `tests/test_strategic_warfare_ai_policy.py` and `tests/test_strategic_warfare_system.py`.

## Phase 7: User Story 6 - Continue Pending Strikes After Save/Load and Replay (Priority: P1)

**Goal**: Pending orders, defense state, deterministic seed, and consequences produce the same results after every existing persistence path.

**Independent Test**: Save or encode a pending strike, restore it, advance to resolution, and compare orders, defense attempts, impacts, notifications, and relations.

- [x] T014 [P] [US6] Add save/load, snapshot, Arrow IPC, and ordered-action replay continuation coverage in `tests/test_strategic_warfare_persistence.py`.
- [x] T015 [US6] Confirm all strategic tables are registered for the existing serializers in `modules/base/schema.py` and `tests/test_strategic_warfare_persistence.py`.

## Phase 8: User Story 7 - Inspect Launch Readiness and Defense (Priority: P2)

**Goal**: The military overview shows payload options, weapon readiness/range, launch eligibility guidance, pending state, defense coverage/interception estimate, and recent outcomes without mutating authoritative state.

**Independent Test**: Presenter and mocked-UI tests show the data for selected and unselected targets and preserve hidden launch information for unauthorized viewers.

- [x] T016 [P] [US7] Add presenter projections for production eligibility, launch hints, and target-specific defense coverage/estimate in `src/client/ui/panels/military/presenter.py`.
- [x] T017 [US7] Render production queue/action, payload options, timing, validation guidance, coverage, and estimates in `src/client/ui/panels/military/strategic_warfare_panel.py`.
- [x] T018 [P] [US7] Add read-only presenter and mocked-ImGui coverage in `tests/test_strategic_warfare_panel.py`.
- [ ] T019 [US7] Complete rendered-client SC-006 and SC-010 acceptance using `specs/110-strategic-warfare-and-missile-defense/quickstart.md`.

## Phase 9: Polish and Cross-Cutting Verification

**Purpose**: Verify focused behavior, full-suite integration, and the recorded performance budget.

- [x] T020 [P] Run the focused strategic warfare suite from `specs/110-strategic-warfare-and-missile-defense/quickstart.md` and record the result there.
- [x] T021 Run the repository-wide automated suite and record failures separately from live-client acceptance in `specs/manual-acceptance-blockers.md` (2026-10-07: 917 passed, 25 skipped, 239 subtests passed; no test failures; 116 warnings; 832.53 seconds).
- [x] T022 Confirm SC-007 remains supported by the already recorded three-iteration measurements in `specs/110-strategic-warfare-and-missile-defense/research.md`; do not start a fourth optimization iteration.

## Dependencies and Execution Order

- Setup/schema task T002 precedes launch timing T005–T006 and persistence T014–T015.
- US1 precedes US2 because launch validation relies on research and configured assets.
- US2 precedes defense, impact, notification, and persistence continuation tests.
- US3 precedes impact/effect verification; US4 and US5 share the resolved-order lifecycle.
- US7 can proceed after the domain projections are stable; rendered acceptance T019 requires a running client.
- Final focused/full suite tasks follow implementation changes. SC-007's existing measurement is evidence only; its optimization allowance is exhausted.

## Parallel Opportunities

- T003, T008, and T010 are separate test additions within the same test module and should be applied in sequence if editing that shared file; they can be reviewed independently.
- T014 persistence tests and T016 presenter projections touch separate files and can be reviewed independently after T002/T006 contracts stabilize.
- T018 panel tests can be authored independently from the server-side persistence tests.
- Do not run a fourth optimization iteration for SC-007 while working on any parallel task.

## Parallel Execution Examples

After the shared schema/action fields are stable, independent work can proceed in separate files:

```text
Task: T014 persistence continuation tests in tests/test_strategic_warfare_persistence.py
Task: T016 read-only preview projections in src/client/ui/panels/military/presenter.py
Task: T018 mocked-panel tests in tests/test_strategic_warfare_panel.py
```

Keep edits to `tests/test_strategic_warfare_system.py` sequential because multiple story test tasks share that file.

## Implementation Strategy

Complete the authoritative P1 loop first: research/configuration, launch validation/timing, defense, bounded effects, and persistence. Then complete the client overview. Run focused tests after each logical change, followed by repository-wide tests. Leave T019 open until rendered acceptance is actually performed; headless tests do not satisfy it. No task in this plan authorizes multiplayer or editor-only implementation.

## Phase 10: Convergence

- [x] T023 Enable scenario-configured ICBM and SLBM design profiles with class-specific range, payload cap, research, readiness, flight timing, and defense interaction per FR-002 (partial); verified by `test_scenario_enabled_slbm_uses_its_profile_and_resolves_through_defense`.
- [x] T024 Apply bounded civilian population impact to the authoritative age-band columns present in the region schema and test those columns per FR-009 (partial); verified by `test_civilian_impact_changes_authoritative_population_age_bands`.
