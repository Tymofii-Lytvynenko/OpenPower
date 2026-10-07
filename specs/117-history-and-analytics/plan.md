# Implementation Plan: History and Analytics

**Branch**: `117-history-and-analytics` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

## Summary

Implement an append-oriented history layer that observes configured authoritative and derived indicators, captures attributable domain events, and exposes deterministic trends, comparisons, rankings, timelines, cause trails, and CSV inspection. The simulation records history after campaign setup; client analytics remain read-only and operate on synchronized state snapshots.

## Technical Context

**Language/Version**: Python 3.14.1
**Primary Dependencies**: Polars DataFrames, Apache Arrow IPC, existing ImGui client, pytest
**Storage**: Typed `GameState` tables synchronized and persisted through existing IPC/save paths
**Testing**: pytest unit/integration tests plus opt-in scale benchmark
**Target Platform**: Existing OpenPower desktop client and authoritative simulation process
**Project Type**: Data-oriented desktop strategy game
**Performance Goals**: A 10-million-snapshot selected-series/ranking query below 500 ms; latest recorded ranking measurement is 2.67 ms on the revision-matched series index
**Constraints**: History is observational and must not modify authoritative gameplay values or future outcomes; deterministic ordering and explicit unit/completeness rules; preserve stable subject IDs after entity removal
**Scale/Scope**: Country, region, relationship, military, demographic, economic, political, diplomatic, strategic, event, and war-history observations. Multiplayer and game-editor-only functionality are excluded by [implementation-scope.md](../implementation-scope.md).

## Constitution Check

- **Layer separation**: History recording stays in `modules/base/systems/world/history_system.py`; UI/query analytics belong to the client. `HistoryQueryService` was moved out of `src/shared` because calculation/query logic is not a passive shared contract. The module system imports only permitted shared contracts.
- **Data-oriented state**: Definitions, series indexes, snapshots, and event evidence are typed Polars tables in the existing `GameState`; IPC/save serialization is reused.
- **Composition and SOLID**: Recording is a registered `ISystem`; query logic is a dedicated read-only service; the panel composes selectors and render helpers without simulating state.
- **Commenting**: Comments remain English and explain rationale for non-obvious identity, normalization, and incremental-processing decisions.
- **Empirical verification**: Focused regression and persistence tests plus the 10-million-row opt-in benchmark provide runtime evidence. Human-visible client workflow is tracked separately and will not be inferred from headless tests.

## Design Decisions

- Current state remains authoritative. A history row records an observation or source event, never a command that changes simulation state.
- Sampling is triggered by changed source revisions or the configured due boundary. Retention and deterministic downsampling are applied per series.
- Missing, stale, derived, and authoritative records remain distinguishable; unavailable measurements are not converted to zero.
- Comparisons use a common evaluation boundary. Same-unit series preserve values; incompatible units may only be indexed to a first positive value when each series keeps a stable unit through that boundary. Rankings exclude incompatible units rather than compare raw magnitudes.
- Event/cause links are recorded only when published source evidence exists. Unknown causes remain unknown.
- Ranking uses the persisted series state only when its revision matches the snapshot table; otherwise it computes a common boundary from snapshots.

## Project Structure

```text
modules/base/systems/world/history_system.py       # incremental authoritative recorder
modules/base/schema.py                             # typed history tables and keys
modules/base/registration.py                       # system registration
src/client/services/history_query_service.py       # read-only query, ranking, export
src/client/ui/panels/service/history_panel.py      # player-facing analytics
src/client/ui/layouts/game_panel_registry.py       # in-game panel registration
tests/test_history_system.py                       # recording, determinism, persistence
tests/test_history_panel.py                        # presentation contract regressions
tests/test_history_performance.py                  # opt-in 10-million-row gate
```

**Structure Decision**: Reuse the existing simulation module, shared typed table registry, client service/panel composition, GameState IPC, and persistence boundaries. No new engine loop, editor flow, or multiplayer transport is introduced.

## Constitution Gate

The initial design gates pass. The only discovered layer violation was the analytics query implementation under `src/shared`; it has been moved to `src/client/services/history_query_service.py`. Final verification must include history tests and layer-boundary tests. The manual 60-second client workflow remains a human-visible acceptance gate if no game session is available.
