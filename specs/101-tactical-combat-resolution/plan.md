# Implementation Plan: Tactical Combat Resolution MVP

**Branch**: `101-tactical-combat-resolution` | **Date**: 2026-08-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/101-tactical-combat-resolution/spec.md`

## Summary

Extend the existing server-authoritative military simulation with explicit unit readiness, timed readiness transitions, allied participation in two-sided battles, a queryable battle-status view, and occupation updates after victory. Stable readiness is stored on each unit; an active transition is represented by a persisted start/end interval so progress and ETA are deterministic. Orders that require a different posture are queued behind the transition or rejected according to the order contract. Combat continues to use the existing engagement discovery and deterministic resolution policy, adding readiness-weighted contributions and side membership without introducing terrain, regional fortification, supply, or logistics data.

The implementation will preserve existing action/event compatibility, keep gameplay policy in `modules/base`, expose passive contracts through `src/shared`, and make the client render snapshots rather than mutate simulation state.

## Technical Context

**Language/Version**: Python 3.11

**Primary Dependencies**: Polars for state tables, NumPy for numeric helpers, PyArrow-compatible snapshot serialization, Arcade/OpenGL and `imgui_bundle` for the desktop client, and the Python standard library for the current test suite.

**Storage**: In-memory Polars `DataFrame` tables in `GameState`, persisted through the existing save/snapshot path. No new database or external service is required.

**Testing**: `unittest` discovery and focused test modules. Determinism tests compare serialized table/event output from identical inputs; UI-facing contracts are tested with snapshot fixtures and presenter-level tests.

**Target Platform**: Windows desktop client with a headless/server simulation loop; the simulation must remain runnable without a graphics context.

**Project Type**: Desktop strategy game engine with layered shared contracts, server systems, client renderers/controllers, and data-driven module systems.

**Performance Goals**: Keep the fixed-step server update non-blocking for the client; resolve and publish 100 concurrent active engagements in a validation scenario without quadratic work in readiness processing; keep readiness progress derivation O(number of transitioning units); consume a representative snapshot within a bounded headless client update without graphics or network I/O.

**Constraints**: Server-authoritative state; deterministic results for identical state, actions, and time; passive stdlib-only contracts in `src/shared`; server-owned save migration and snapshot compatibility; gameplay policy in `modules/base`; strict client observation; English-only code comments; no terrain classification, regional fortification level, supply factor, full logistics, routing, pathfinding, or more than two opposing battle sides in this MVP.

**Scale/Scope**: Existing unit and battle tables, three stable readiness statuses (`PARKED`, `READY`, `FORTIFIED`), one active transition per unit, two battle sides with multiple country participants per side, and occupation state for regions won in combat.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|-----------|-------|--------|
| Layer separation | Shared actions/events/view contracts remain passive; save migration/compatibility stays in `src/server`; readiness, ally eligibility, combat, and occupation policy stay in `modules/base`; client only presents snapshots and emits actions. | PASS |
| Data-oriented state | Additive Polars schemas and keyed tables hold unit transitions, battle participants/status, and occupations; no per-entity mutable service graph is introduced. | PASS |
| Modularity and SOLID | Transition timing, side resolution, combat contribution, and view projection are separate policies with stable inputs; existing systems are extended through composition/helpers rather than inheritance. | PASS |
| Determinism | Transition completion is derived from simulation time, battle grouping uses stable sorted keys, and events are emitted once per state change. | PASS |
| Commenting and maintainability | New comments explain policy decisions in English only; self-documenting names are preferred and no external product is referenced in comments. | PASS |
| Empirical verification | Focused unit, integration, contract, save/load, and performance smoke tests are planned before implementation is considered complete. | PASS |

**Gate status before Phase 0**: PASS — all constitutional constraints are addressed by the specification and this plan.

**Gate status after Phase 1 design**: PASS — feature-specific validation is server-owned, shared contracts remain passive, and no violation requires a complexity exception.

## Project Structure

### Documentation (this feature)

```text
specs/101-tactical-combat-resolution/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── unit-readiness.md
│   ├── battle-events.md
│   └── battle-status-view.md
└── tasks.md                 # created later by $speckit-tasks
```

### Source Code (repository root)

```text
src/shared/
├── actions.py                # readiness action and existing movement/attack actions
└── events.py                 # readiness and battle lifecycle events

src/server/
└── state_migrations.py       # legacy defaults and save/snapshot compatibility validation

modules/base/
├── schema.py                 # shared table schemas and keys
└── systems/military/
    ├── military_system.py    # order gating, pending orders, unit posture fields
    ├── readiness_system.py   # timed transitions and progress derivation
    ├── combat_system.py      # two-side battle grouping and deterministic rounds
    ├── alliance_policy.py    # eligible allied participant resolution
    └── occupation_system.py  # controller/occupation updates after victory

src/client/
├── controllers/
│   ├── unit_interaction_controller.py
│   └── viewport_controller.py
├── views/
│   └── game_view.py
├── renderers/
│   ├── map_renderer.py       # political/battle overlay updates
│   └── unit_renderer.py      # status icon/progress overlay and battle markers
└── ui/
    ├── components/hud/unit_context_menu.py
    └── panels/
        ├── unit_details_window.py
        ├── region_inspector.py
        └── military/
            ├── battle_overview_panel.py
            ├── presenter.py
            └── unit_list_panel.py

tests/
├── test_unit_readiness.py
├── test_order_readiness.py
├── test_battle_allies.py
├── test_battle_status_interface.py
├── test_occupation_resolution.py
├── test_snapshot_protocol.py
├── test_tactical_combat_fixtures.py
├── test_tactical_combat_performance.py
├── test_client_snapshot_performance.py
├── test_combat_system.py     # preserve and extend existing coverage
└── test_engagement_mvp.py    # preserve movement/contact behavior
```

**Structure Decision**: Keep the current layered desktop/server project. New military policies are isolated under `modules/base/systems/military`; passive actions, events, and view contracts live under `src/shared`; save migration and compatibility validation live under `src/server`; existing client controllers, renderers, presenters, and panels consume authoritative snapshots. The existing snapshot codec remains a transport boundary and receives regression coverage rather than gameplay policy. No new top-level application or service is introduced.

## Implementation Phases

### Phase 0 — Research and decisions

1. Record the readiness timing, interruption, pause, and save/load decisions in `research.md`.
2. Record the deterministic two-side/allied-participant algorithm and battle lifecycle semantics.
3. Record the client refresh strategy and test approach, including alternatives rejected for this MVP.

### Phase 1 — Design and contracts

1. Define additive unit, transition, pending-order, battle, participant, and occupation tables in `data-model.md`.
2. Define action/state/event payloads and idempotency rules in `contracts/unit-readiness.md` and `contracts/battle-events.md`.
3. Define the read-only UI projection and refresh behavior in `contracts/battle-status-view.md`.
4. Provide executable validation scenarios and expected outcomes in `quickstart.md`.

### Phase 2 — Implementation sequencing

1. Add passive actions/events and schema columns without changing existing action signatures; keep schema migration out of `src/shared`.
2. Implement readiness transition policy and persisted progress/ETA updates.
3. Add pending-order gating and cancellation rules for movement, attack, and fortified posture.
4. Extend combat grouping to exactly two sides, resolve eligible allies, apply readiness contribution weights, and publish lifecycle events/status rows.
5. Add occupation updates while preserving political ownership.
6. Add server-owned legacy migration/default validation, then update client presentation for unit progress and battle status; refresh overlays on relevant snapshot changes.
7. Add focused tests, run the existing regression suite, then run the 100-engagement server and bounded client snapshot performance smoke tests.

### Phase 3 — Verification and handoff

1. Run all commands in `quickstart.md` on a headless server context.
2. Verify deterministic replay, transition timing, event uniqueness, ally eligibility, and occupation behavior.
3. Verify client progress/battle views with a snapshot fixture and ensure no client-side state mutation is introduced.
4. Generate `tasks.md` from these artifacts with `$speckit-tasks`; implementation begins only after the dependency-ordered task list is reviewed.

## Complexity Tracking

No constitutional violations are known. No complexity exception is required.
