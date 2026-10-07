# Tasks: Campaign Scenarios, Objectives, and Advisor

**Input**: Design documents in `specs/116-campaign-scenarios-objectives-and-advisor/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/campaign-actions-and-overview.md`, `quickstart.md`

## Phase 1: Baseline and traceability

- [X] T001 [P] Map each FR/SC/acceptance scenario to current implementation and test evidence in `specs/116-campaign-scenarios-objectives-and-advisor/coverage.md`; run the focused baseline command from `quickstart.md`.
- [X] T002 Verify campaign tables, bootstrap/post-process order, and registration/persistence contracts in `modules/base/schema.py`, `modules/base/registration.py`, `tests/test_schema_mod_migrations.py`, and `tests/test_game_state_ipc.py`.

## Phase 2: User Story 1 — Start a scenario once (Priority: P1)

**Goal**: Apply only validated setup and create the campaign and objectives for an eligible actor before the first actionable update.

**Independent Test**: Start selectable and unavailable scenarios; verify all supported setup targets apply exactly once and invalid configuration leaves authoritative tables unchanged.

- [X] T003 [P] [US1] Add scenario actor/scope, whitelisted setup-table, setup-once, invalid JSON/field, and sandbox edge tests in `tests/test_campaign_system.py`.
- [X] T004 [US1] Close demonstrated start/selection gaps in `modules/base/systems/world/campaign_system.py` and `src/client/views/new_game_view.py`; preserve the all-or-nothing setup validation contract.

## Phase 3: User Story 2 — Measure objective progress (Priority: P1)

**Goal**: Evaluate every declared objective type from authoritative sources and expose current/target/remaining values, evidence, and missing-data reasons.

**Independent Test**: Cover every supported objective type and prove metrics come from the owning source table; missing sources block visibly instead of fabricating a value.

- [X] T005 [P] [US2] Add table-driven measurements for region control/conquest, treaty membership, resource quantity/share, GDP per capita, research, strategic construction/use, and unavailable sources in `tests/test_campaign_system.py`.
- [X] T006 [US2] Correct only measurement gaps proven by T005 in `modules/base/systems/world/campaign_objective_policy.py`; retain source-table/unit evidence and avoid duplicating domain calculations.

## Phase 4: User Story 3 — Track holds, deadlines, and outcomes (Priority: P1)

**Goal**: Apply objective state transitions, hold reset/decay, required/optional rules, deadlines, win/loss/draw ordering, and sandbox continuation deterministically.

**Independent Test**: Replay identical boundary inputs and verify identical progress/evidence/outcomes, including objective completion at a deadline and a temporarily lost control condition.

- [X] T007 [P] [US3] Add tests for all objective states, hold reset/decay, deadline expiry, optional objectives, simultaneous win/loss/draw conditions, and transition reasons in `tests/test_campaign_system.py`.
- [X] T008 [US3] Close demonstrated progress/outcome gaps in `modules/base/systems/world/campaign_system.py` while keeping objective evaluation before outcome and advisor evaluation.

## Phase 5: User Story 4 — Delegate bounded authority (Priority: P2)

**Goal**: Persist country, ruling-party, and active treaty-sphere delegation without exceeding explicit authority or scope.

**Independent Test**: Activate and return each supported scope, then prove AI context contains only delegated domains and valid current targets; invalid actors/scopes change no authoritative state.

- [X] T009 [P] [US4] Extend authorization, priority, return-condition, invalid-scope, and idempotent delegation tests in `tests/test_campaign_system.py` and `tests/test_ai_policies.py`.
- [X] T010 [US4] Correct proven delegation/authority gaps in `modules/base/systems/world/campaign_system.py` and `modules/base/systems/world/ai_system.py` without granting implicit ownership or multiplayer behavior.

## Phase 6: User Story 5 — Receive advisor guidance (Priority: P2)

**Goal**: Project prioritized contextual recommendations from messages, news, objective changes, deadlines, and domain signals; stale guidance must not issue actions.

**Independent Test**: For each configured high-priority signal, assert source, reason, affected actor/region, confidence/urgency, expiry, optional action, and stale/resolved transition.

- [X] T011 [P] [US5] Add signal-family and recommendation-lifecycle tests in `tests/test_campaign_system.py`, including news, deadlines, objective changes, and invalidated recommendations.
- [X] T012 [US5] Close demonstrated advisor signal or lifecycle gaps in `modules/base/systems/world/campaign_system.py`; preserve recommendations as informational proposals.

## Phase 7: User Story 6 — Review campaign progress (Priority: P1)

**Goal**: Show the latest actor campaign, actionable objectives/deadlines, delegation, outcomes, and active advisor priorities through the existing passive-client boundary.

**Independent Test**: Verify country-scoped presenter output, all required objective fields, stable sorting, and action dispatch only for the current authorized actor.

- [X] T013 [P] [US6] Add presenter and panel-model tests for current/target/remaining, held time, deadline, outcome, delegation, and advisor urgency in `tests/test_campaign_presenter.py` and `tests/test_objectives_panel.py`.
- [X] T014 [US6] Correct campaign overview projection/rendering gaps in `src/client/ui/panels/service/campaign_presenter.py`, `src/client/ui/panels/service/objectives_panel.py`, and `src/client/views/new_game_view.py` without direct state mutation.

## Phase 8: User Story 7 — Persist and replay campaign state (Priority: P1)

**Goal**: Reproduce scenario setup provenance, objective progress/evidence, delegation, recommendations, deadlines, and outcomes after save/load, snapshots, IPC, and ordered-action replay.

**Independent Test**: Continue equivalent campaign states after each persistence path and compare campaign-owned rows and subsequent deterministic transitions.

- [X] T015 [P] [US7] Add campaign continuation/save/load/snapshot/IPC and deterministic action-replay coverage in `tests/test_campaign_persistence.py`.
- [X] T016 [US7] Fix any persistence/migration gaps proven by T015 in `modules/base/schema.py`, `src/server/io/save_writer.py`, and `src/server/io/data_load_manager.py`, preserving existing shared serialization contracts.

## Phase 9: Polish and acceptance

- [X] T017 [P] Record an FR/SC-to-file/test coverage matrix and remaining manual acceptance in `specs/116-campaign-scenarios-objectives-and-advisor/coverage.md`.
- [X] T018 Re-run the focused quickstart command and relevant schema, AI, IPC, save, and layer-boundary tests; record exact outcomes in `specs/116-campaign-scenarios-objectives-and-advisor/research.md`.
- [X] T019 Verify the existing 10,000-objective/5,000-signal performance evidence and carry the 3-iteration limit forward; do not run another optimization iteration in `tests/test_campaign_performance.py`.
- [ ] T020 Complete 30-second campaign overview usability acceptance in a rendered desktop client; headless tests do not satisfy this manual criterion.

## Dependencies and execution order

- T001 and T002 establish evidence and contracts before implementation.
- User Stories 1–3 are the P1 simulation core and are sequential: setup creates objectives, then objective transitions feed outcomes.
- User Stories 4–5 depend on active campaign context but can be tested independently after the foundational contracts.
- User Story 6 depends on stable campaign records and is client-only over those records.
- User Story 7 validates all persisted state after functional behavior stabilizes.
- T019 consumes the already-completed performance evidence in `research.md`; this performance algorithm has used all three optimization iterations and must not receive a fourth.
- T020 remains external/manual if no rendered desktop client is exposed.

## Implementation strategy

Preserve the existing architecture and passing behavior. Complete the traceability audit first, write or strengthen a focused failing test before each functional change, and only change the layer that owns the demonstrated gap. Treat the existing passing performance gate as closed to further tuning. Finish with the quickstart suite and mark manual UI acceptance separately.
