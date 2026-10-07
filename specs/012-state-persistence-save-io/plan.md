# Implementation Plan: State Persistence, Parquet Save/Load & Static Data Ingestion

**Branch**: `012-state-persistence-save-io` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/012-state-persistence-save-io/spec.md`

## Summary

Complete the save/load and static-ingestion contracts using the existing `GameState`, `DataLoader`, `SaveWriter`, save migration registry, and Polars/Parquet format. Ensure the live new-game path loads definition tables before entities and world relations, validate persistent-field round trips and interrupted slot replacement, and keep malformed assets diagnosable rather than silently becoming empty world data. Measure save/load performance on a representative production state before considering any algorithm tuning.

## Technical Context

**Language/Version**: Python 3.10+; local runtime Python 3.14.1

**Primary Dependencies**: Polars, Apache Arrow/Parquet, orjson, rtoml, Pillow, pytest

**Storage**: `user_data/saves/<slot>/` directories with `meta.json`, per-field Parquet files, and `tables/*.parquet`; static data under each resolved mod's `data/` tree

**Testing**: pytest unit/integration tests; temporary project roots for save lifecycle tests; an opt-in timed save/load probe against the real loaded world

**Target Platform**: Windows desktop application with a background authoritative server; save directories remain on one filesystem for rename-based replacement

**Project Type**: Python desktop grand-strategy game with modular server/data-loading layers

**Performance Goals**: Save under 300 ms and load under 500 ms for the representative full initial campaign state; correctness and atomic recovery are hard gates

**Constraints**: Preserve existing gameplay state and mod precedence; serialize only fields marked persistent; retain save-format migrations; staging and target directories must share a filesystem; stop after at most three measured optimization iterations per algorithm and record any unmet gate before moving on

**Scale/Scope**: Full base world plus active mod layers, all persistent `GameState` fields, current save format and legacy v1-to-v2 migration

## Constitution Check

- **Layer separation**: Pass. Persistence and static ingestion remain in `src/server/io`; shared schemas/state stay in `src/shared`; save path helpers remain in `src/core`.
- **Data-oriented contracts**: Pass. World entities and relations remain Polars DataFrames; DataFrames use Parquet rather than being expanded into JSON.
- **Composition/SOLID**: Pass. `SaveStateLoader` delegates to `DataLoader`; the live new-game loader composes static definition loading without duplicating parsing policy.
- **Commenting**: Pass. New comments will explain compatibility/atomicity rationale in English only.
- **Empirical verification/anti-masking**: Pass after round-trip, failure-injection, migration, asset-layering, and measured save/load checks. Invalid required source data must surface a diagnostic rather than silently produce an empty substitute.

## Project Structure

```text
src/core/saves.py
src/shared/state.py
src/shared/migrations.py
src/server/io/save_writer.py
src/server/io/save_loader.py
src/server/io/data_load_manager.py
src/server/io/static_loader.py
src/server/io/migrations.py
tests/test_save_writer_atomicity.py
tests/test_save_loader_type_hints.py
tests/test_data_loader_mod_layering.py
tests/test_headless_simulation.py
specs/012-state-persistence-save-io/
```

**Structure Decision**: Keep `DataLoader` as the current session composition boundary for both save restoration and initial world compilation. Reuse the existing `StaticAssetLoader` definition parsing capability from that path; do not create a second persistence format or alter gameplay tables. Maintain the thin `SaveStateLoader` facade for callers that need a save-only interface.

## Design Decisions

1. The persistent/transient annotations on `GameState` are the serialization authority; reflection must not serialize transient event/action buses or internal schema caches.
2. The save bundle remains a directory with Parquet table payloads and a versioned JSON metadata file. Save into a unique sibling staging directory, retain a hidden backup during replacement, and restore it if installing the staged generation fails.
3. Existing v1 saves migrate through the ordered `MigrationRegistry`; newer unsupported versions fail explicitly.
4. Static ingestion uses three dependency phases: definition tables first, entities second, and world relations last. Regions keep the BGR-compatible 24-bit ID formula and mod override order; country extension files merge by `id`.
5. Parser/corruption diagnostics remain visible. Do not substitute empty datasets after a required asset parse failure; optional/missing asset directories may still produce the documented empty table.
6. Performance baselines are recorded before any optimization. A still-failing gate after at most three measured changes becomes a documented future issue; no fourth iteration is allowed in this pass.

## Complexity Tracking

No constitution violations are introduced.
