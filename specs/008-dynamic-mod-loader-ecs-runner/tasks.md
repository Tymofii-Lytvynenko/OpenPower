# Tasks: Dynamic Mod Loader and ECS Runner

## Phase 1: Manifest and registration compatibility

- [X] T001 Verify deterministic dependency expansion and missing/cyclic manifest diagnostics in `src/shared/mods.py` and `tests/test_mod_manager.py`.
- [X] T002 Accept current `contribute()` and legacy `register()` entry points; warn and skip absent registration files/functions in `src/engine/mod_manager.py`.
- [X] T003 Apply later-module system replacement by ID with an override warning; reject duplicate declarations within one module in `src/engine/mod_manager.py`.
- [X] T004 Verify contribution API normalization, schema/migration aggregation, legacy entry points, and override diagnostics in `tests/test_mod_manager.py` and `tests/test_mod_api.py`.

## Phase 2: Deterministic ECS scheduler

- [X] T005 Use `graphlib.TopologicalSorter` while maintaining deterministic phase/ID ordering among ready systems in `src/engine/simulator.py`.
- [X] T006 Log cycle participants at critical level and raise `CycleError` before system execution; cover stable order and cycle diagnostics in `tests/test_engine_determinism.py`.
- [X] T007 Confirm engine content-agnostic imports through `tests/test_layer_boundaries.py`.

## Phase 3: Acceptance verification

- [X] T008 Add and run the opt-in cold scan/import/registration/graph benchmark; measured 179.678 ms for the base mod and 30 systems.
- [X] T009 Rerun the full repository suite after the loader/scheduler changes: `684 passed, 16 skipped, 116 warnings, 190 subtests passed in 162.89s`.

## Exit criteria

Loader API compatibility, deterministic topological ordering, diagnostics, SC-003 startup timing, and the full-suite gate are complete.
