# Tasks: Battle Strategy and Force Posture

**Input**: Design documents in `specs/115-battle-strategy-and-force-posture/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/battle-command-and-summary.md`, `quickstart.md`

## Phase 1: Setup and baseline

- [x] T001 [P] Record benchmark workload, environment, five samples, and passing baseline in `specs/115-battle-strategy-and-force-posture/research.md` and `tests/test_battle_strategy_performance.py`.

## Phase 2: Foundational contracts

- [x] T002 Verify table schemas, system registration/order, and resolver projection consumption in `modules/base/schema.py`, `modules/base/registration.py`, `modules/base/systems/military/battle_strategy_system.py`, and `modules/base/systems/military/combat_system.py`.

## Phase 3: User Story 1 — Issue authorized force strategies (Priority: P1)

**Goal**: Apply bounded posture intent only to the authorized country's selected force types; expand presets without replacing valid specific orders.

**Independent Test**: Run posture and combat tests proving each posture changes the documented resolver projection, unauthorized commands are side-effect free, force-type filters are respected, and specific orders outrank presets.

- [x] T003 [P] [US1] Add action tests for all supported postures, force-type scoping, and allied-country isolation in `tests/test_battle_strategy_system.py` and `tests/test_battle_allies.py`.
- [x] T004 [P] [US1] Add preset default/per-type projection and specific-order precedence tests in `tests/test_battle_strategy_system.py`.
- [x] T005 [US1] Reject unsupported preset entries with a visible per-force reason and deterministic command status in `modules/base/systems/military/battle_strategy_system.py` and `tests/test_battle_strategy_system.py`.

## Phase 4: User Story 2 — Withdraw and reorganize forces (Priority: P1)

**Goal**: Back-off, retreat, regroup, and return through existing route/readiness rules without changing battle identity or restoring a concluded fight.

**Independent Test**: Continue retreat state from snapshot and disk save, complete its route/regroup/return transitions, and verify invalid routes or concluded battles cancel safely.

- [x] T006 [P] [US2] Test back-off, safe-location reorganization cost/duration, retreat route block, and battle-conclusion interruption in `tests/test_battle_strategy_system.py`.
- [x] T007 [US2] Test retreat/posture/route persistence and deterministic next transition across IPC and disk saves in `tests/test_battle_strategy_persistence.py`.

## Phase 5: User Story 3 — Occupy cleared territory without annexation (Priority: P1)

**Goal**: Establish military control only after authorized occupation conditions pass, preserving political ownership and rejecting hostile survivors.

**Independent Test**: Accept a valid occupation command over eligible stationed regions; reject unauthorized, non-hostile, surviving-hostile, and unsupported-region cases without state mutation.

- [x] T008 [P] [US3] Add occupation acceptance/rejection, multiple-stationed-region, and unchanged-owner assertions in `tests/test_battle_strategy_system.py` and `tests/test_occupation_resolution.py`.
- [x] T009 [US3] Correct any occupation-condition gaps demonstrated by T008 in `modules/base/systems/military/battle_strategy_system.py` and `tests/test_battle_strategy_system.py`.

## Phase 6: User Story 4 — Review authorized battle commands and outcomes (Priority: P1)

**Goal**: Show participating force posture/history and completed losses only to authorized viewers, while marking aggregate balance as an estimate.

**Independent Test**: Compare an authorized participant's view with a nonparticipant's view; only the authorized view contains detailed participants, positions, and losses.

- [x] T010 [P] [US4] Add viewer-authorization regression tests for battle existence, force groups, command history, and casualty detail in `tests/test_battle_visibility.py`.
- [x] T011 [US4] Add viewer-scoped battle presenter projections and wire the current player's country into `src/client/ui/panels/military/presenter.py`, `src/client/ui/panels/military/battle_overview_panel.py`, and `src/client/ui/core/panel_context.py` only if required by the tests.
- [x] T012 [US4] Verify battle summary outcome, participants, force-type positions, losses, issuer/effective time, and estimate label in `tests/test_battle_visibility.py` and `tests/test_battle_status_interface.py`.

## Phase 7: User Story 5 — Use the same battle rules under AI control (Priority: P2)

**Goal**: Have AI-controlled countries use the shared authoritative battle-strategy action and respect player/delegation authority.

**Independent Test**: An AI participant proposes one deterministic posture action for its own active force type, and the registered battle-strategy system applies or rejects it through the normal command path.

- [x] T013 [P] [US5] Add deterministic posture candidate and authority/delegation tests in the focused `tests/test_battle_strategy_ai.py` suite for `modules/base/systems/world/ai/battle_strategy_policy.py`.
- [x] T014 [US5] Register the policy in `modules/base/systems/world/ai/__init__.py` and `modules/base/systems/world/ai_system.py`; verify action dispatch in `tests/test_ai_integration.py`.

## Phase 8: Polish and empirical acceptance

- [x] T015 Run the 10,000-posture/2,000-battle benchmark in `tests/test_battle_strategy_performance.py` and record exact results in `specs/115-battle-strategy-and-force-posture/research.md`. The gate passed; no optimization iteration was used.
- [x] T016 Run every automated functional command in `specs/115-battle-strategy-and-force-posture/quickstart.md`; record exact outcomes in `specs/115-battle-strategy-and-force-posture/research.md`.
- [ ] T017 Complete interactive battle-overview usability acceptance in a desktop client and record evidence in `specs/115-battle-strategy-and-force-posture/research.md`; headless tests are not a UI pass. **External/manual**: Computer Use exposed no desktop apps; native app control is disabled in this session.

## Dependencies and execution order

- T001 and T002 precede story work; T002 confirms the current contracts before changing implementation.
- User Stories 1–4 build on the shared posture/authority contract. US2 and US3 are independently testable after the foundation; US4 must use the final authorization rule.
- US5 depends on the authoritative `ActionSetBattleStrategy` contract from US1 and the shared AI authority filter.
- T015 stops as soon as the gate passes. T016 follows functional stabilization. T017 requires a targetable interactive client.

## Implementation strategy

Preserve existing passing behavior. Add tests for unsupported or unverified cases first; change the smallest owning module only when a test demonstrates a specification gap. Do not spend optimization iterations on a passing baseline. Complete P1 command, retreat, occupation, and authorized-summary stories before considering any tuning work.

## Phase 9: Convergence

- [x] T018 [FR-003/FR-004] Add bounded attack-risk, readiness, holding, and counterattack projections and consume them in the existing battle resolver with distinct-posture tests.
- [x] T019 [FR-005/FR-006/FR-018] Complete disengagement and retreat lifecycle behavior, including explicit battle exit after regrouping, route-block recovery, and persistence tests.
- [x] T020 [FR-012] Extend AI posture decisions to use retreat and reorganization where their shared lifecycle conditions allow, then verify authority and action dispatch.
- [x] T021 [FR-019] Distribute eligible occupation forces through valid movement/access routes; establish/refresh occupation records without changing sovereignty or bypassing route constraints.
- [x] T022 [FR-011/FR-020/SC-006] Show battle outcome and each own force's next posture action in the authorized overview; verify victor, force positions, losses, issuer, effective time, and estimate labeling.
- [x] T023 [FR-009 and edge cases] Enforce scenario-level command constraints and deterministic same-boundary order precedence; prove rejected orders leave authoritative tables and revisions unchanged.
- [x] T024 [FR-014] Verify command replay reproduces posture projections and next transitions in addition to existing save/load and IPC continuation tests.
- [x] T025 [FR-015] Record full-table posture/lifecycle scanning as deferred performance debt while the sub-500 ms gate passes; revisit dirty-set processing after functional convergence and allow no more than three measured optimization iterations.
