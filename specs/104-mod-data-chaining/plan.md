# Implementation Plan: Mod Data Chaining Engine

**Branch**: `104-mod-data-chaining` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

## Summary

Validate and order active module dependencies before runtime contributions or world loading; layer Polars datasets and assets deterministically; reject missing, cyclic, schema-invalid, or engine-incompatible configurations with actionable diagnostics. The implementation reuses the existing `GameConfig`, `ModManager`, static loader, and module contribution contracts rather than introducing a second loader.

## Technical Context

**Language/Version**: Python 3.10+ (validated in this workspace on 3.14.1)

**Primary Dependencies**: Polars 1.36.1, rtoml, pytest; existing module API and schema/migration registries.

**Storage**: `mods.json`, per-module `mod.toml`, layered `modules/<id>/data`, and `modules/<id>/assets`.

**Testing**: pytest unit/integration tests; opt-in deterministic 25-mod startup/merge benchmark.

**Target Platform**: Windows and Linux desktop; load order must be deterministic independent of filesystem iteration order.

**Project Type**: Python game engine with client, authoritative server, engine, shared contracts, and dynamically registered gameplay modules.

**Performance Goals**: Resolving a 25-mod chain and merging its representative world table in under 1.5 seconds. The existing controlled benchmark recorded a 20.06 ms median; correctness remains independent of benchmark timing.

**Constraints**: Resolve prerequisites and compatibility before state allocation; child layers must preserve unrelated rows and fields; retain current schemas, module API, asset fallback, localization override, and system-registration behavior.

**Scale/Scope**: Up to 25 active mods for the measured startup gate; dependency chains of 10+ layers; table overlays include region/country records and keyed world relations.

## Constitution Check

- Layer boundaries: PASS. Dependency and manifest decisions use the existing shared mod contract; runtime contributions stay in `src/engine`; table parsing and validation stay in `src/server/io`; presentation assets/localization remain path-resolved through `GameConfig`.
- Data/schema contracts: PASS. Mod data remains Polars-backed and schema registration/migrations are composed through `ModRuntime` before simulation startup.
- Modularity and composition: PASS. `ModManager` composes contribution systems, schemas, and migrations; static loading is separate from runtime registration.
- Empirical verification: PASS WITH GATES. Automated coverage and the 25-mod benchmark are runnable locally; the benchmark is opt-in and must be reported separately from correctness tests.

## Architecture and Project Structure

The current architecture remains the source of truth:

- `src/shared/mods.py`: manifest model, discovery, compatibility validation, deterministic dependency ordering.
- `src/shared/config.py`: active-chain paths, asset precedence, and base-to-child localization merge.
- `src/engine/mod_manager.py`: compatibility/API validation and ordered runtime contribution composition.
- `src/server/io/data_load_manager.py`, `src/server/io/static_loader.py`: non-destructive keyed table overlays and static definitions/world ingestion.
- `tests/test_mod_manager.py`, `tests/test_game_config.py`, `tests/test_data_loader_mod_layering.py`, `tests/test_mod_data_chaining_performance.py`: focused acceptance coverage.

**Structure Decision**: Extend these existing components and their tests. Do not add a parallel mod registry, duplicate manifest parser, or client-side simulation authority.

## Delivery Phases

1. Verify manifest validation, dependency DAG ordering, deterministic ordering, and fail-fast startup diagnostics.
2. Verify keyed TSV/TOML/Parquet overlays retain unrelated records and apply child values only where supplied.
3. Verify base fallback, active-mod asset priority, localization merge, and ordered system/schema/migration contributions.
4. Run the focused correctness suites and isolated 25-mod benchmark; document actual results without tuning a passing gate.
