# Tasks: History and Analytics

**Input**: Design documents from `specs/117-history-and-analytics/`

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/history-analytics.md`, `quickstart.md`

**Tests**: Required by the user's repository-wide implementation request; regression tasks are included below.

**Organization**: One independently testable player story: inspect history, compare subjects, rank indicators, trace recorded events, and export evidence.

## Phase 1: Setup

**Purpose**: Establish typed persistence surfaces and system registration.

- [X] T001 [P] Define the four typed history tables and primary keys in `modules/base/schema.py`.
- [X] T002 [P] Register `HistorySystem` in the base module post-process order in `modules/base/registration.py`.

## Phase 2: Foundational

**Purpose**: Deliver incremental observation and deterministic evidence storage used by the player workflow.

- [X] T003 Implement default indicator definitions, revision/due-boundary observation, stable series IDs, missing markers, and retention/downsampling in `modules/base/systems/world/history_system.py`.
- [X] T004 Implement idempotent domain-journal and economic-cause ingestion with source evidence in `modules/base/systems/world/history_system.py`.

## Phase 3: User Story 1 — Inspect and compare historical outcomes (Priority: P1)

**Goal**: A player can inspect historical indicators and evidence, compare subjects at compatible boundaries, understand rankings, and export selected records without affecting gameplay.

**Independent Test**: Given controlled country, region, relation, and event data, the recorder creates deterministic typed rows; queries return correct current values, gaps, common-boundary comparisons, unit-safe rankings, chronological timelines, and CSV; the gameplay panel exposes these read-only actions; all state survives save/load and yields the same continuation.

### Tests for User Story 1

- [X] T005 [P] [US1] Test observations, derived indicators, source immutability, due/change/missing boundaries, and compaction in `tests/test_history_system.py`.
- [X] T006 [P] [US1] Test deterministic comparison/ranking, common boundaries, units, ties, freshness, relationship events, and causes in `tests/test_history_system.py`.
- [X] T007 [P] [US1] Test line/step gaps, subject identity, comparison/ranking display, and CSV clipboard behavior in `tests/test_history_panel.py`.
- [X] T008 [US1] Test IPC, save/load, event deduplication, and deterministic continuation in `tests/test_history_system.py`.

### Implementation for User Story 1

- [X] T009 [US1] Keep the simulation recorder in the module layer and place read-only history queries in `src/client/services/history_query_service.py`.
- [X] T010 [US1] Implement player-facing history controls, trends, comparisons, rankings, timelines, and export in `src/client/ui/panels/service/history_panel.py` and register the panel in `src/client/ui/layouts/game_panel_registry.py`.
- [X] T011 [US1] Add the opt-in 10-million-snapshot ranking gate in `tests/test_history_performance.py`; record the measured result and avoid extra tuning after the gate passes in `specs/117-history-and-analytics/research.md`.
- [X] T012 [US1] Run focused history, IPC, persistence, and layer-boundary validation and record results in `specs/117-history-and-analytics/quickstart.md` and `specs/117-history-and-analytics/coverage.md`.
- [ ] T013 [US1] Perform the desktop history workflow from `specs/117-history-and-analytics/quickstart.md` and record the human-visible 60-second cause-trail outcome in `specs/117-history-and-analytics/quickstart.md`.

## Dependencies

```text
T001 + T002 -> T003 + T004
T005 + T006 -> T009
T007 -> T010
T003 + T004 + T009 + T010 -> T008 + T011 -> T012 -> T013
```

## Parallel Opportunities

- T001 and T002 touch different files and have no dependency on one another.
- T005/T006 and T007 can be implemented as tests in distinct files; implementation of the recorder and query service remains sequential within its source files.
- The single user story is complete once automated validation and the desktop acceptance check pass.

## Implementation Strategy

1. Keep the schema and registration prerequisites stable.
2. Validate observation, event, and retention behavior before expanding the client workflow.
3. Deliver deterministic query behavior before UI wiring.
4. Verify IPC/save-load/replay and the opt-in scale gate.
5. Finish with both automated regressions and the human-visible client check; do not infer the latter from headless tests.

## Progress

- Automated implementation and validation tasks T001–T012 are complete. The focused matrix on 2026-10-07 reported **40 passed, 1 opt-in benchmark skipped** in 3.92 seconds. The existing 10-million-snapshot benchmark record is **2.67 ms**, below the 500 ms target; no additional optimization iteration was performed.
- T013 remains open because the current environment has no active desktop game session. Keep this acceptance gate open until a human-visible check is run.
