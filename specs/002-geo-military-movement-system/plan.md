# Implementation Plan: Geo-Coordinated Military Movement & Pathfinding

**Branch**: `002-geo-military-movement-system` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-geo-military-movement-system/spec.md`

## Summary

Implement deterministic, permission-aware movement as gameplay policy in the base military module, using the core geographic projection for spherical distance and the existing shared action/state contracts. The route planner selects a least-cost path with a stable tie-break, the movement system advances authoritative route legs and validates them again at arrival, and the client presents the accepted route and order feedback without mutating simulation state. Existing readiness, production, diplomacy, save/IPC, and mod-schema behavior remains authoritative.

## Technical Context

**Language/Version**: Python 3.10+; repository CI/runtime currently includes Python 3.11 and 3.14.

**Primary Dependencies**: Polars 1.36.1, NumPy and the existing OpenGL/ImGui client stack; no new runtime dependency.

**Storage**: Authoritative in-memory Polars tables in `GameState`, serialized through the existing Arrow IPC/save pipeline.

**Testing**: pytest; unit tests for geographic math/policies, integration tests through `MilitarySystem` and `GameState`, presentation tests for route projection, plus an opt-in workload benchmark.

**Target Platform**: Existing desktop client and headless simulation process on supported Python platforms.

**Project Type**: Layered Python game engine with a dynamically registered gameplay module.

**Performance Goals**: Preserve the specification target of less than 2 ms for a 10,000-unit movement/manpower tick; measure it using a reproducible benchmark. Route planning is command-driven and must remain deterministic. Client rendering remains within the existing frame budget.

**Constraints**: Haversine calculations use a 6,371 km Earth radius; baseline duration is clamped to 360–10,080 simulation minutes. Movement must not bypass readiness or change ownership on rejected orders. Gameplay policy stays in `modules/`; geographic mechanisms stay in `src/core/`; UI remains a passive action sender and snapshot renderer. Multiplayer is outside this feature.

**Scale/Scope**: Global region adjacency, 10,000 military units, multiple independently authorized groups, changing war/treaty rights, and scenario-configurable movement modifiers.

## Constitution Check

- **Layer separation — PASS**: geographic calculation is reusable core logic; routing, permissions, readiness, recruitment, and invasion constraints are module policy; the client only sends actions and projects snapshots.
- **Data-oriented state — PASS**: simulation state is represented by the existing Polars tables and schema migration/IPC mechanisms.
- **Composition and SOLID — PASS**: `MilitarySystem` composes route, access, duration, readiness, unit-factory, and invasion policies instead of embedding every decision in one algorithm.
- **Commenting and maintainability — PASS**: preserve self-documenting names; add English comments only for non-obvious rationale or bug fixes.
- **Empirical verification — GATE**: formula, acceptance, persistence, and performance behavior must be tested; the `<2 ms` target remains unproven until the benchmark passes on a recorded runtime.

No architectural exception is proposed. The current implementation is the starting point and must be assessed against each requirement rather than assumed complete.

## Design Decisions

1. Reuse `EquirectangularProjection.geo_distance_km` as the single spherical-distance mechanism; keep movement duration modifiers in military policy.
2. Use deterministic least-cost graph search and a lexicographic route tie-break. When a legacy scenario has no adjacency data, preserve the existing direct-route compatibility path; explicit routes still require adjacency when it is available.
3. Revalidate access, domain compatibility, and invasion conditions at each route boundary so changed world state cannot authorize an illegal crossing or landing.
4. Store accepted routes and their feedback in schema-backed `unit_movement_routes` and `unit_order_feedback` tables; the client consumes these snapshots.
5. Keep recruitment as a compatibility action while production/deployment orders remain separate domain flows.

## Project Structure

### Documentation (this feature)

```text
specs/002-geo-military-movement-system/
├── plan.md
├── research.md
├── data-model.md
├── contracts/
│   └── movement.md
├── quickstart.md
└── tasks.md
```

### Source Code

```text
src/
├── core/map/geo.py
├── shared/actions.py
└── client/
    ├── controllers/unit_interaction_controller.py
    ├── renderers/unit_renderer.py
    └── ui/panels/military/presenter.py

modules/base/
├── schema.py
├── registration.py
└── systems/military/
    ├── military_system.py
    ├── route_policy.py
    ├── movement_access.py
    ├── naval_invasion_policy.py
    └── readiness_system.py

tests/
├── test_military_route_policy.py
├── test_movement_access.py
├── test_naval_invasion_policy.py
├── test_order_readiness.py
├── test_military_route_presenter.py
└── test_military_movement_spec.py
```

**Structure Decision**: Extend the existing layered single-project structure. No new package, persistence backend, or engine-loop change is required; tests live beside the repository's existing pytest suite.

## Complexity Tracking

No constitution violations or added architectural complexity require an exception.

## Update-local routing indexes

`MilitaryRoutePlanner.prepare()` materializes region topology once for repeated searches in one `MilitarySystem.update()`. `RegionRouteSnapshot` and `RegionTravelTime` provide lazy region/home/coordinate indexes for covert routing. The objects are discarded after the update so later map or ownership changes are visible. The prepared graph caches topology only: per-order access, unit-domain checks, and segment costs still run for each search. This preserves the route legality contract while avoiding repeated full-world materialization.
