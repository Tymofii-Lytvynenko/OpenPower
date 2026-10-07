# Tasks: State Persistence, Parquet Save/Load & Static Data Ingestion

**Input**: Design documents from `specs/012-state-persistence-save-io/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`

## Phase 1: Setup

**Purpose**: Confirm existing test/runtime support; no dependency or project scaffolding changes are expected.

- [X] T001 [P] Record Python, Polars, PyArrow, orjson versions and available storage context in `specs/012-state-persistence-save-io/performance-log.md` before measuring persistence gates.

## Phase 2: Foundational contracts

**Purpose**: Define one small representative persistent-state fixture that later save/load tests can reuse.

- [X] T002 [P] Add a reusable representative `GameState` fixture with persistent tables, dataclasses, globals, and system state in `tests/test_save_writer_atomicity.py`.

## Phase 3: User Story 1 — Save and restore a campaign (Priority: P1)

**Goal**: Round-trip all persistent state, preserve the old slot across failed replacement, and keep migrations/recovery explicit.

**Independent Test**: Temporary-root tests prove persistent-field fidelity, transient exclusion, invalid-name rejection, rollback, backup recovery, and migration behavior without using a real user save directory.

### Tests for User Story 1

- [X] T003 [P] Test full persistent-field round-trip and transient-field exclusion in `tests/test_save_writer_atomicity.py`.
- [X] T004 [P] Test that `SaveWriter.save_game` rejects noncanonical/path-traversal names in `tests/test_save_writer_atomicity.py`.
- [X] T005 [P] Test v1-to-v2 migration and unsupported future-version failure in `tests/test_save_writer_atomicity.py`.
- [X] T006 [P] Test that corrupt save-list metadata is skipped with a diagnostic in `tests/test_save_writer_atomicity.py`.

### Implementation for User Story 1

- [X] T007 Use the shared canonical-name validator in `src/server/io/save_writer.py` while preserving the `bool` failure contract.
- [X] T008 Add visible diagnostics for corrupt save metadata in `src/core/saves.py` without exposing an invalid slot as valid data.
- [X] T009 Fill any serialization/reflection gaps exposed by T003–T006 in `src/server/io/save_writer.py`, `src/server/io/data_load_manager.py`, or `src/shared/migrations.py`.
- [X] T010 Run save lifecycle, reflection, migration, and existing persistence regressions in `tests/test_save_writer_atomicity.py`, `tests/test_save_loader_type_hints.py`, `tests/test_migration_integration.py`, and the focused persistence tests.

## Phase 4: User Story 2 — Compile a complete modded world (Priority: P2)

**Goal**: Make the production new-game path load definition TOMLs before entities and world relations, while preserving mod overrides and current adjacency/resource/schema enrichment.

**Independent Test**: A temporary two-mod fixture loaded through `DataLoader.load_initial_state` contains `def_*`, normalized/deduplicated regions, merged countries, and flattened world relations in dependency order.

### Tests for User Story 2

- [X] T011 [P] Test definitions-first loading through the production `DataLoader` path in `tests/test_data_loader_mod_layering.py`.
- [X] T012 [P] Test TOML list/entity/matrix parsing, hex normalization with and without `#`, and BGR-compatible runtime IDs in `tests/test_data_loader_mod_layering.py`.
- [X] T013 [P] Test malformed required TSV/TOML inputs identify their source path rather than yielding an empty substitute in `tests/test_data_loader_mod_layering.py`.

### Implementation for User Story 2

- [X] T014 Reuse definition parsing from `src/server/io/static_loader.py` in phase one of `src/server/io/data_load_manager.py` without dropping adjacency, geography, resource, or schema tables.
- [X] T015 Replace parse-error empty fallbacks for required static inputs with path-specific failures in `src/server/io/data_load_manager.py` and `src/server/io/static_loader.py`.
- [X] T016 Run static-loader layering, schema, resource, and initial-state integration tests in `tests/test_data_loader_mod_layering.py` and related focused suites.

## Phase 5: Polish and empirical gates

**Purpose**: Validate the success criteria and document any unresolved target without exceeding the optimization limit.

- [X] T017 Add an opt-in serialization-only save/load benchmark against the production initial world in `tests/test_save_io_performance.py`; keep simulation ticks outside the timed region.
- [X] T018 Run the benchmark and record samples, median/p95, workload, storage, and hardware in `specs/012-state-persistence-save-io/performance-log.md`; if a target fails, allow no more than three measured optimization iterations per algorithm, document each outcome, and then move on.
- [X] T019 Run the commands in `specs/012-state-persistence-save-io/quickstart.md`, mark implementation tasks complete, and keep any inconclusive full-simulation throughput result explicitly separate.

## Dependencies and execution order

- T001–T002 establish measurements and fixtures before story tests.
- T003–T006 precede their corresponding save/load fixes T007–T009; T010 validates User Story 1.
- T011–T013 precede the static-ingestion fixes T014–T015; T016 validates User Story 2.
- T017–T018 run after correctness work; T019 is the final cross-cutting check.
- User Story 2 depends only on the shared fixture/environment, not on User Story 1 runtime changes.

## Parallel opportunities

- T003–T006 use separate test cases and may be authored independently before the shared serializer fixes.
- T011–T013 cover independent static-ingestion acceptance cases and may be authored independently.
- Runtime changes T007–T009 and T014–T015 are sequential because they share core persistence/loader entry points.

## Implementation strategy

1. Establish test setup and representative fixtures.
2. Complete the P1 save/restore contract and its focused tests.
3. Complete P2 static ingestion through the live session loader.
4. Measure save/load after correctness is stable; tune only when a clean baseline misses a gate, and stop after three iterations.
5. Run the quickstart and preserve full-simulation throughput as a separate measurement.
