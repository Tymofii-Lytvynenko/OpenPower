# Tasks: Headless Simulation Runner and Determinism Comparison

**Input**: Current-state documentation for code already present in `src/simulation/` and
the `openpower sim` CLI.

**Status note**: Implementation checkboxes below record code and test artifacts observed
in the repository. They do not claim a test run during this documentation update.

## Phase 1: Existing implementation baseline

- [X] T001 Create a headless `GameSession` from the selected project, module set, save,
  player, duration, and seed in `src/simulation/runner.py`.
- [X] T002 Load and schedule supported semantic actions from JSON in
  `src/simulation/actions.py`.
- [X] T003 Write configuration, timeline, snapshots, final reports, and optional state
  tables through `src/simulation/artifacts.py` and `src/simulation/snapshots.py`.
- [X] T004 Inspect runtime and state integrity diagnostics in
  `src/simulation/diagnostics.py` and fingerprint persistent state in
  `src/simulation/fingerprint.py`.
- [X] T005 Expose run and repeated-run comparison commands through `src/cli.py`,
  `src/simulation/runner.py`, and `src/simulation/comparison.py`.
- [X] T006 Keep focused coverage in `tests/test_headless_simulation.py` and
  `tests/test_simulation_tooling.py`.

## Phase 2: Acceptance recording

- [ ] T007 Run the commands in `quickstart.md` and record the actual exit statuses,
  fingerprints, and output artifact paths.
- [ ] T008 Record whether a same-seed comparison matches and whether a deliberately
  divergent state is reported with a nonzero result.

## Requirement Traceability

| Requirement | Tasks |
| --- | --- |
| FR-001 | T001 |
| FR-002 | T002 |
| FR-003 | T003 |
| FR-004 | T004 |
| FR-005 | T004, T007 |
| FR-006 | T005, T008 |
| FR-007 | T003 |
