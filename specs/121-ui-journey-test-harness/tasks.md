# Tasks: UI Journey Test Harness

**Input**: Current-state documentation for the registered UI surface and journey tooling.

**Status note**: Implementation checkboxes below record code and test/data artifacts
observed in the repository. They do not claim a test run during this documentation update.

## Phase 1: Existing implementation baseline

- [X] T001 Register discoverable surface definitions in `src/client/ui/testing/catalog.py`.
- [X] T002 Build deterministic inputs and render a selected surface in
  `src/client/ui/testing/fixtures.py`, `harness.py`, and `surface.py`.
- [X] T003 Apply ordered interaction journeys and capture results in
  `src/client/ui/testing/journey.py` and `driver.py`.
- [X] T004 Capture screenshots and compare them with optional baselines in
  `src/client/ui/testing/surface.py` and `visual_diff.py`.
- [X] T005 Run surface suites in isolated child processes, write suite summaries, and
  rerun failed pairs through `src/cli.py`.
- [X] T006 Provide a live Arcade input smoke path through
  `src/client/ui/testing/live_smoke.py` and `src/cli.py`.
- [X] T007 Keep focused harness coverage in `tests/test_ui_testability.py` and maintain
  fixture/journey resources under `tests/ui/`.
- [X] T008 Retain the budget-panel shortcut and viewport validation through
  `src/client/ui/testing/budget.py` and `src/cli.py`.

## Phase 2: Acceptance recording

- [ ] T009 Run one headless journey, a four-size matrix, failed-run recovery, and live
  smoke workflow; record their reports, screenshots, statuses, and environment in
  `docs/UI_TESTING.md`.

## Requirement Traceability

| Requirement | Tasks |
| --- | --- |
| FR-001 | T001 |
| FR-002, FR-003 | T002, T003 |
| FR-004 | T004 |
| FR-005, FR-006 | T005 |
| FR-007 | T002, T005 |
| FR-008 | T006, T009 |
| FR-009 | T002–T005 |
| FR-010 | T008 |
