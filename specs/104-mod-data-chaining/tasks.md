# Tasks: Mod Data Chaining Engine

**Input**: Design documents from `specs/104-mod-data-chaining/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

## Phase 1: Setup

**Purpose**: Capture the performance environment and reuse existing project test infrastructure.

- [X] T001 [P] Record Python/Polars versions, thread count, and the 25-mod workload/results in `specs/104-mod-data-chaining/research.md`.

## Phase 2: Foundational validation

**Purpose**: Verify mod metadata and dependency diagnostics before data or runtime initialization.

- [X] T002 [P] Test manifest/API/engine-version validation and missing/circular dependency diagnostics in `tests/test_mod_manager.py` and `tests/test_game_config.py`.

## Phase 3: User Story 1 — Activate and combine a mod chain (Priority: P1)

**Goal**: Resolve a deterministic dependency chain and apply its content, assets, and runtime contributions without losing unrelated base data.

**Independent Test**: A temporary base/child mod fixture resolves dependencies, patches a keyed row, retains unreferenced rows/columns, uses child asset/localization precedence, and registers contributions in the same validated order.

### Tests for User Story 1

- [X] T003 [P] [US1] Test deterministic topological ordering, transitive prerequisites, deep chains, missing parents, and cycles in `tests/test_mod_manager.py`.
- [X] T004 [P] [US1] Test keyed TSV/TOML/Parquet data overlays and schema-safe preservation of unrelated region/country/world records in `tests/test_data_loader_mod_layering.py`.
- [X] T005 [P] [US1] Test high-priority asset fallback and base-to-child localization merging in `tests/test_game_config.py`.
- [X] T006 [P] [US1] Test engine/API compatibility fails before registration import or initial-state allocation in `tests/test_mod_manager.py` and `tests/test_session_startup.py`.
- [X] T007 [P] [US1] Test ordered system contributions, intentional cross-mod replacement, same-mod duplicate rejection, schema registration, and save-migration aggregation in `tests/test_mod_manager.py` and `tests/test_schema_mod_migrations.py`.

### Implementation for User Story 1

- [X] T008 Acceptance suite exposed no correctness gaps in the named source files; no implementation changes were needed.
- [X] T011 Load layered language/religion profiles before bootstrap, normalize accepted profiles, and verify source-year/provenance plus child replacement in `src/server/io/static_loader.py`, `src/server/io/data_load_manager.py`, and `tests/test_data_loader_mod_layering.py`.
- [X] T012 Verify keyed extension records with duplicate keys collapse to one merged row while retaining the last non-null extension values in `tests/test_data_loader_mod_layering.py`.

## Phase 4: Empirical gates and final verification

**Purpose**: Verify the measured startup bound and run the feature regressions.

- [X] T009 Run the isolated 25-mod dependency/table-merge benchmark in `tests/test_mod_data_chaining_performance.py`; record samples, median/p95, host, and thread count in `specs/104-mod-data-chaining/research.md`. Allow at most three measured optimization iterations only if the 1.5-second gate fails. Gate passed; no tuning performed.
- [X] T010 Run the commands in `specs/104-mod-data-chaining/quickstart.md`, record exact results, and update this checklist with any remaining external gate. Functional suite: 49 passed, 1 skipped; isolated benchmark: 1 passed.

## Dependencies and execution order

- T001 establishes measurement context.
- T002–T007 are independent acceptance tests and precede any source correction in T008; T011–T012 add the layered-profile and duplicate-key cases to the same user story.
- T009 runs after correctness is stable; a passing benchmark requires no tuning.
- T010 is the final feature validation and follows T011–T012.

## Parallel opportunities

- T003–T007 can be authored/run independently where they touch separate test files.
- T008 is sequential after the acceptance tests to avoid changing already-correct behavior.

## Implementation strategy

1. Validate metadata and dependency failure paths.
2. Verify data, asset/localization, and runtime-contribution behavior independently.
3. Correct only observed functional gaps; retain existing public APIs and schemas.
4. Run the 25-mod benchmark once after correctness and stop if its gate passes.
