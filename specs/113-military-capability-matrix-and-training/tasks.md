# Tasks: Military Capability Matrix and Training

**Input**: Design documents from `specs/113-military-capability-matrix-and-training/`

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, and `quickstart.md`.

**Tests**: Required by the specification and the implementation objective. The latest combined focused run passed 108 tests, one default-skipped opt-in performance test, and 40 subtests across AI, military capability/training, combat, intelligence, IPC, and layer-boundary coverage. SC-007 passes its isolated benchmark; live-client acceptance remains open because no targetable desktop client window was available.

## Phase 1: Existing foundation

**Purpose**: Preserve and verify current module-layer capabilities and contracts.

- [X] T001 [P] Define canonical land, air, naval, and strategic role profiles with bounded capability and training/research transforms in `modules/base/systems/military/capability_catalog.py`; validate catalog behavior in `tests/test_capability_catalog.py` (included in the 31 focused feature tests passed on 2026-10-07).
- [X] T002 [P] Keep research funding, design prerequisites, cost, and production orders in `modules/base/systems/military/research_program_system.py`; verify unlock/queue behavior in `tests/test_research_program_system.py` (included in the 15-test focused run).
- [X] T003 Register `unit_training_orders` and `unit_capability_projections` as keyed authoritative Polars tables in `modules/base/schema.py`; retain the projection contract used by `modules/base/systems/military/combat_system.py` and `modules/base/systems/military/military_system.py` (covered by the 21-test focused run).
- [X] T004 [US1] Implement basic authorized training, off-map lifecycle, timed progress, pause/resume, cancellation, and deployment return in `modules/base/systems/military/capability_system.py`; verify in `tests/test_military_capability_system.py` (included in the 15-test focused run).
- [X] T005 [P] Display design role, domain, capabilities, target interactions, prerequisites, cost, and maintenance in `src/client/ui/panels/military/unit_design_panel.py` and show training status in `src/client/ui/panels/military/presenter.py` (UI runtime acceptance remains open below).

## Phase 2: User Story 1 — Inspect, research, design, train, and employ forces (Priority: P1)

**Goal**: Make role-specific characteristics, research, training, counters, intelligence, and enemy estimates inspectable and deterministic without changing the existing battle lifecycle.

**Independent Test**: Focused requirement tests prove design gating, training lifecycle, target eligibility, privacy-safe estimates, and save/load determinism without requiring a world-scale run; live UI checks are recorded separately.

- [X] T006 [P] [US1] Add capability metadata for value units, fixed/variable status, bounds, prerequisite, production effect, zero semantics, and interaction meaning in `modules/base/systems/military/capability_catalog.py`; assert complete metadata coverage in `tests/test_capability_catalog.py` (validated in the focused 43-test run on 2026-10-07).
- [X] T007 [US1] Enforce each attacker's configured target matrix at the per-force damage projection in `modules/base/systems/military/combat_system.py`; add mixed-role, invalid-target, neutral, and bounded-counter cases to `tests/test_combat_system.py` without changing battle identity, sides, readiness timing, occupation, or ownership (validated in the focused 43-test run on 2026-10-07).
- [X] T008 [US1] Add scenario/mod-configurable training-site and instructor capacity fields to `modules/base/schema.py` and validate deterministic local-site/domain/capacity eligibility in `modules/base/systems/military/capability_system.py`; cover unavailable site, no instructor, exhausted capacity, funding, and preserved progress in `tests/test_military_capability_system.py` (validated by 13 focused training/IPC tests on 2026-10-07).
- [X] T009 [US1] Persist assigned training site, training location, progress, cost, and start/pause/resume/completion/cancellation history in `modules/base/schema.py` and `modules/base/systems/military/capability_system.py`; verify active/paused/completed IPC snapshot and deterministic continuation cases in `tests/test_military_capability_system.py` and `tests/test_game_state_ipc.py` (13 passed on 2026-10-07).
- [X] T010 [P] [US1] Add deterministic aggregate role-count estimates to military espionage findings in `modules/base/systems/military/covert_operations_system.py`, preserving source telecom/coverage confidence and omitting unit IDs/design records; cover seeded estimation and privacy in `tests/test_covert_operations_system.py` (included in the 31 focused feature tests passed on 2026-10-07).
- [X] T011 [US1] Build a read-only foreign force estimate projection in `src/client/ui/panels/military/presenter.py` that applies owner/discovery/treaty authorization, confidence, freshness, and stable best-source selection; cover unknown/stale/multiple-source/allied cases in `tests/test_military_presenter.py` (included in the 31 focused feature tests passed on 2026-10-07).
- [X] T012 [US1] Display estimated role and strength ranges with source, confidence, freshness, and explicit unknown/outdated state in `src/client/ui/panels/military/unit_list_panel.py`; add passive-render/presenter coverage in `tests/test_military_presenter.py` and `tests/test_military_panels.py` (included in the 31 focused feature tests passed on 2026-10-07).
- [X] T013 [US1] Connect readiness changes to the existing intelligence/event contracts so eligible foreign observers can detect bounded mobilization signals in `modules/base/systems/military/covert_operations_system.py` and `src/client/ui/panels/military/presenter.py`; cover assignment authority, treaty sharing/confidence caps, deterministic results, and unit/cell non-disclosure in `tests/test_covert_operations_system.py`, `tests/test_military_presenter.py`, and `tests/test_military_panels.py` (focused signal/presenter/UI tests passed on 2026-10-07).
- [X] T014 [US1] Make AI capability, design, and training decisions use the same authority, facility, funding, research, and eligibility rules as human actions in `modules/base/systems/world/ai/military_policies.py`; verify deterministic accepted/rejected actions in `tests/test_ai_policies.py` (AI procurement filters locked designs, and AI training proposals share the authoritative facility/cost rules and action handler; verified in the 102-test, 40-subtest combined run on 2026-10-07).
- [X] T015 [US1] Verify that capability effects only alter documented battle projections and leave battle identity, sides, readiness lifecycle, occupation, and sovereignty unchanged in `tests/test_combat_system.py` and `tests/test_battle_strategy_system.py` (paired baseline/projection regression passed in the 66-test, 34-subtest focused run on 2026-10-07).
- [X] T016 [US1] Add seeded rerun, save/load, snapshot synchronization, and replay parity for design availability, training, estimates, and projections in `tests/test_military_capability_system.py`, `tests/test_game_state_ipc.py`, and `tests/test_engine_determinism.py` (design IDs/prerequisites, training progression, foreign estimates, capability projections, military IPC records, and equivalent engine snapshots are compared in the 102-test, 40-subtest run on 2026-10-07).
- [X] T017 [US1] Verify every default role has a fixed/variable profile, bounded capability projection, valid target set, vulnerability/counter relationship, and domain-specific comparison in `tests/test_capability_catalog.py`; label fixed role interactions separately from adjustable design values in `src/client/ui/panels/military/unit_design_panel.py` and cover the distinction in `tests/test_military_panels.py` (11 catalog/panel tests and 34 catalog subtests passed on 2026-10-07).

## Phase 3: Incremental processing and empirical validation

**Purpose**: Verify change-scoped projection work and SC-007 without weakening functional semantics.

- [X] T018 [US1] Add an opt-in deterministic 50,000-unit/10,000-design benchmark with 5% changed records in `tests/test_military_capability_performance.py`; profile the current projection path, then implement change-scoped invalidation in `modules/base/systems/military/capability_system.py`. Allow no more than three measured algorithm-optimization iterations, record each changed approach and comparable result in `specs/113-military-capability-matrix-and-training/research.md`, and keep SC-007 open if iteration three still exceeds 1 second (iteration 1 passes at 705.466 ms median / 916.620 ms p95).
- [ ] T019 [US1] Run the design, training, intelligence-sharing, stale-observation, and mixed-role battle acceptance workflows in `specs/113-military-capability-matrix-and-training/quickstart.md` in the running desktop client; record actual outcomes without substituting headless tests for the UI gate.
- [X] T020 Run all feature-focused tests and the quickstart in `specs/113-military-capability-matrix-and-training/quickstart.md`; record exact outputs and leave any unverified live-client or performance gate open in `specs/113-military-capability-matrix-and-training/tasks.md` (108 passed, 1 opt-in benchmark skipped by default, 40 subtests; quickstart commands: 27 passed/34 subtests and 14 passed; SC-007 separately passed; live-client T019 remains open).
- [X] T021 [US1] Synthesize an explicit `unknown` foreign-force view for active wartime opponents without an authorized current observation in `src/client/ui/panels/military/presenter.py`; display it as unknown, never zero, in `src/client/ui/panels/military/unit_list_panel.py`, with authorized-source and no-war regression cases in `tests/test_military_presenter.py` and `tests/test_military_panels.py` (8 focused presenter/panel tests passed before follow-up signal coverage on 2026-10-07).

## Deferred performance issues

| Issue | Current evidence | Optimization iterations | Next action |
|---|---|---:|---|
| SC-007 capability projection update | Controlled baseline was 3,855.657 ms median / 4,033.897 ms p95. Iteration 1 change-scoped projection cache measured 705.466 ms median / 916.620 ms p95 on the same workload; gate passes. | 1/3 | Keep the opt-in benchmark as a regression gate. Do not spend additional tuning iterations unless a future comparable measurement fails. |
| AI training/procurement candidate scans | AI training materializes/sorts the unit table daily; procurement materializes design prerequisite metadata on its cadence. No workload benchmark or slowdown evidence exists. | 0 | Include in normal-workload profiling before optimizing; implementation correctness remains the priority. |
| FR-015 research/intelligence no-op work | One change-scoped implementation now skips research action materialization on idle ticks, filters readiness observations to event-referenced units/designs, avoids reading finding rows without readiness events, and suppresses unchanged covert-table revisions. Correctness passed; no elapsed-time baseline or speedup is claimed. | 1/3 | If profiling later shows this path remains costly, establish a comparable workload baseline before any further changes; allow at most two additional algorithm iterations and defer with attempt/result evidence after the third. |

Live-client acceptance (T019) remains open: the desktop automation inventory returned no targetable native application window, so the interactive steps were not attempted and no headless test is being counted as UI evidence. Quickstart automated outputs are recorded in `research.md`; T020 is complete with the performance result recorded separately.

## Dependencies and execution order

- T006–T007 define capability/interaction semantics; T015 verifies they do not mutate the existing battle lifecycle.
- T008–T009 extend the existing training record; T014 consumes the same action and eligibility contract for AI.
- T010 precedes T011–T012 because the presenter must consume persisted intelligence observations rather than live enemy units.
- T013 feeds the same authorized estimate path and can proceed after the readiness event contract is established.
- T016 and T019 depend on the functional tasks above. T018 follows the functional work and must obey the three-iteration budget.
- T020 is the final feature-level validation task.

## Parallel opportunities

- T006 and T010 touch separate catalog and intelligence source files and can proceed independently.
- T008 and T007 touch training and combat components, respectively, but should integrate through stable schemas before shared test-state changes.
- T011–T012 share presenter/UI behavior and should be completed in order; tests in distinct feature modules may proceed independently after their contracts settle.

## Implementation strategy

Complete missing functional semantics first: capability metadata/interactions, training-site eligibility, and authorized foreign estimates. Then close persistence, AI, and invariant coverage. Profile SC-007 only after correctness is established, cap algorithm optimization at three measured iterations, and defer the gate with evidence rather than delaying remaining specifications. Live-client acceptance remains a separate final gate.

## Phase 4: Convergence

- [X] T022 Gate research action processing and mobilization-intelligence scans on relevant actions/events, scope work to affected records, and avoid unchanged table rebuilds per FR-015 (partial); add no-op, changed-state, snapshot-continuation, and deterministic replay tests in `tests/test_research_program_system.py`, `tests/test_covert_operations_system.py`, and `tests/test_game_state_ipc.py` (validated with 106 tests and 40 subtests on 2026-10-07).
