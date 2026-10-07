# Tasks: Demographics and Time Simulation

## Phase 1: Clock and compatibility contracts

- [X] T001 Cover speed levels, leap-day/date conversion, and boundary events in `tests/test_time_system.py` and `tests/test_population_system.py`.
- [X] T002 Preserve `GAME_EPOCH`, the existing time-event contract, and legacy demographic column defaults in `modules/base/systems/world/time_system.py` and `modules/base/systems/demographics/population_system.py`.

## Phase 2: Deterministic cohort progression

- [X] T003 Verify the one-year birth, aging, and mortality equations against exact expected cohorts in `tests/test_population_system.py`.
- [X] T004 Clamp invalid elapsed duration, per-tick aging/death transitions, and final cohorts so a delayed tick cannot produce negative residents or advance more than one complete source cohort in `modules/base/systems/demographics/population_system.py`.
- [X] T005 Verify large elapsed time and migration separation regressions in `tests/test_population_system.py`.
- [X] T006 Verify focused demographic and time tests; result: 6 passed.

## Phase 3: Scale and full integration

- [X] T007 Add and run an opt-in 10,000-region median benchmark against SC-003 in `tests/test_population_performance.py`; the vectorized cohort fast path measured 1.308, 1.543, 1.318, and 1.297 ms over four consecutive 12-thread runs. The controlled one-thread median was 0.923 ms.
- [X] T008 Run the complete repository suite after the demographic vectorization, identity-cache, and schema-normalization changes; latest result: 684 passed, 16 skipped, 116 warnings, 190 subtests passed in 162.89 s.
- [ ] T009 Run an interactive client scenario to verify pause heartbeat and visible date/speed controls; record this manual gate separately from headless test coverage.
- [X] T010 Stabilize the default 12-thread 10,000-region benchmark so SC-003 passes reproducibly across controlled runs; four consecutive runs on the supported runtime remained below 2 ms.

## Dependencies and exit criteria

The cohort correctness fix is independent of the scale benchmark. Feature completion requires focused regressions, full-suite validation, the SC-003 measurement, and the manual UI check; unmet gates remain open and documented.
