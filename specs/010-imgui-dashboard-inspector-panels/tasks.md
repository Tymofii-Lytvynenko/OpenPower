# Tasks: ImGui Dashboard & Data Inspector Panels

**Input**: Design documents in `specs/010-imgui-dashboard-inspector-panels/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`

## Phase 1: Budget action and controls (US1)

**Goal**: Expose the personal income tax ratio and dispatch it with sector ratios through the existing authoritative action.

- [X] T001 [US1] Add focused tests for syncing, finite clamping, and dispatching tax/sector allocations in `tests/test_budget_panel.py`.
- [X] T002 [US1] Add the personal tax slider and bounded `ActionUpdateBudget` payload construction in `src/client/ui/panels/budget_panel.py`.

## Phase 2: Political weekly drift (US2)

**Goal**: Apply the specified baseline and fallbacks at stable seven-game-day boundaries without removing existing political modifiers.

- [X] T003 [US2] Add exact drift, fallback, missing-column, and non-week-boundary tests in `tests/test_politics_stability_drift.py`.
- [X] T004 [US2] Normalize nullable political inputs, derive weekly cadence from elapsed game days, and correct the drift documentation in `modules/base/systems/politics/politics_system.py`.
- [X] T005 [US2] Update integration fixtures that intentionally exercise weekly politics to use a full game week in `tests/test_political_effect_integration.py`, `tests/test_political_crises.py`, `tests/test_migration_integration.py`, `tests/test_economic_health_integration.py`, and `tests/test_random_event_domain_effects.py`.

## Phase 3: Resource dashboard and ImPlot (US3)

**Goal**: Display production, consumption, imports, exports, and balances in dark metric cards, bars, and a table with visible schema diagnostics.

- [X] T006 [US3] Add pure resource-flow projection and rendering tests in `tests/test_resources_panel.py`.
- [X] T007 [US3] Add snapshot-identity flow caching, dark metric cards, five-series ImPlot bars, and targeted schema diagnostics in `src/client/ui/panels/resources_panel.py`.
- [X] T008 [US3] Add paired ImPlot context ownership and teardown to `src/client/services/imgui_service.py`, `src/client/window.py`, and `src/client/views/editor_view.py`.

## Phase 4: Data inspector (US4)

**Goal**: Preserve the existing searchable, sortable, virtualized Polars grid and verify its visible-row behavior.

- [X] T009 [US4] Verify literal search, stable/nulls-last sorting, dirty sort-spec parsing, and 10,000-row clipping in `tests/test_data_inspector_panel.py`.

## Phase 5: Verification and performance gates

- [X] T010 Run focused feature and regression tests; record the result in `performance-log.md`.
- [ ] T011 Measure 10,000-row end-to-end Data Inspector frame time (<4 ms) on the rendered desktop path; use at most three measured optimization iterations if it fails.
- [ ] T012 Verify slider responsiveness at 60+ FPS and resource chart rendering in a live desktop session; record environment and results.
- [ ] T013 Complete the manual checks in `quickstart.md` and update this task list with evidence.

## Dependencies and execution order

- Phases 1–4 are implemented independently over existing contracts; they were validated together because the resource chart and ImPlot lifecycle share the client frame service.
- T010 depends on T001–T009.
- T011–T013 require a rendered desktop session and remain open until empirical evidence is recorded.

## Performance iteration policy

For each algorithm, record a baseline before tuning and allow no more than three measured changes. If the target remains unmet after iteration three, record all attempts and outcomes in `performance-log.md`, stop optimizing that algorithm, and proceed with remaining specifications.
