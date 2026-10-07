# Implementation Plan: Demographics and Time Simulation

**Branch**: `006-demographics-time-simulation` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

## Summary

Keep time progression and natural cohort changes in the existing `TimeSystem` and `PopulationSystem`. Continue using the canonical `GameTime`, shared events, registered module systems, and the `regions`/`countries` Polars tables. Make elapsed-time handling bounded and deterministic, retain legacy column defaults, and verify the requested 10,000-region tick empirically before claiming the performance criterion.

## Technical Context

**Language/runtime**: Python 3.14; Polars; existing OpenPower ECS/system graph.
**State**: `GameState.time` plus authoritative `regions.pop_14`, `regions.pop_15_64`, and `regions.pop_65` columns.
**Systems**: `base.time` emits shared clock events; `base.population` consumes unpaused real-second events.
**Testing**: pytest unit/integration tests plus an opt-in controlled population benchmark.
**Compatibility**: Missing population columns default to zero; missing fertility and life expectancy use their documented defaults. Time stays anchored to `GAME_EPOCH` and uses `timedelta` for calendar boundaries.
**Performance gate**: SC-003 requires measured median update time below 2 ms for 10,000 regions; benchmark evidence is recorded in [quickstart.md](quickstart.md).

## Constitution Check

- **Layering**: PASS. Simulation behavior remains in the base gameplay module and event/state contracts remain shared.
- **Data-oriented state**: PASS. Regional population columns stay canonical Polars data.
- **Modularity**: PASS. Existing system boundaries are retained; no parallel population or clock service is introduced.
- **Commenting**: PASS. The elapsed-time clamp documents why one delayed tick cannot move more than a complete cohort.
- **Empirical verification**: PARTIAL. Focused tests and the 10,000-region benchmark pass; full-suite and interactive UI gates remain open.

## Design Outputs

- [research.md](research.md): existing clock and demographic behavior and implementation decisions.
- [data-model.md](data-model.md): clock and population state invariants.
- [contracts/time-demographics.md](contracts/time-demographics.md): event and system contracts.
- [quickstart.md](quickstart.md): focused tests, opt-in benchmark, and manual acceptance boundary.
- [tasks.md](tasks.md): dependency-ordered implementation and open empirical gate.

## Structure Decision

Use `modules/base/systems/world/time_system.py` and `modules/base/systems/demographics/population_system.py` in place. Keep API/event definitions in `src/shared`, with tests in `tests/`. Do not move gameplay policy into `src/core`, `src/engine`, or the server.
