# Implementation Plan: Tactical Battle Visualization

**Branch**: `106-tactical-battle-visualization` | **Date**: 2026-08-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/106-tactical-battle-visualization/spec.md`

## Summary

Add a map-anchored, presentation-only battle effect for the existing authoritative `positional` and `assault` combat modes. The simulation will persist one stable geographic anchor per battle, derived from contact coordinates or backfilled from the authoritative region center without using `0,0` as a missing-value sentinel. The client will project that anchor through shared globe occlusion rules and render deterministic passive/active aggregate effects from the smooth presentation clock, independently of unit visibility. Battle panels will use the same Passive/Active terminology, and a local reduced-motion setting will suppress motion without hiding state.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: Polars 1.36.1 / Apache Arrow table contracts, Arcade + OpenGL, `imgui_bundle`, NumPy, existing deterministic political-color and client clock services.

**Storage**: Authoritative in-memory Polars tables with generic Arrow IPC snapshots and existing save/load migrations; local `GameSettings` persistence for reduced motion.

**Testing**: pytest test suite, existing combat/engagement tests, client snapshot/performance harness, and a manual Arcade/ImGui globe smoke test.

**Target Platform**: Desktop client with the server-authoritative simulation process; headless server paths must remain importable and runnable without client dependencies.

**Project Type**: Python desktop grand-strategy game engine with modular simulation and client rendering layers.

**Performance Goals**: Maintain the existing smooth-clock/render performance gate; repeated baseline-versus-feature measurements with 100 visible battles add no more than 5% median frame-time overhead and do not allocate work per participating unit.

**Constraints**: Client is a passive observer; no combat rules, formulas, movement, readiness, ownership, or outcomes change. Effects must obey visible-hemisphere/seam clipping, have bounded screen-space size, be deterministic, and degrade safely for legacy/malformed rows.

**Scale/Scope**: One stable anchor and one aggregate effect per visible battle, two visual sides per battle, existing battle lifecycle and snapshot transport, no terrain/supply/third-side/projectile simulation.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle/gate | Pre-research result | Design result |
|---|---|---|
| Strict layer separation and passive client | Pass: authoritative anchor/mode stay in `modules`/state; client only reads snapshots and settings. | Pass: `BattleEffectRenderer` dispatches no actions and shares no client code with server systems. |
| Data-oriented schemas and Arrow compatibility | Pass: battle data already uses Polars schemas and generic snapshots. | Pass: three additive battle columns plus defaults/validation; no bespoke transport. |
| Modularity, composition, SOLID | Pass: separate anchor policy, shared globe projection, renderer, presenter mapping, and settings preference. | Pass: each component has one responsibility and composes existing clock/color/projection mechanisms. |
| Professional comments and maintainability | Pass: implementation will use self-documenting names and English rationale comments only where needed. | Pass: no external-game references; performance/occlusion work will document the reason, not restate code. |
| Empirical verification and anti-masking | Pass: focused deterministic, integration, projection, and performance tests are planned. | Pass: quickstart includes runnable tests and manual globe/lifecycle verification; malformed rows are isolated rather than silently swallowed. |

No constitutional violation or complexity exception is required.

## Implementation Design

### Phase 0 — research conclusions

The resolved design decisions and alternatives are recorded in [research.md](research.md). The authoritative combat modes are reused, anchors are additive on `battles`, animation is derived from the client presentation clock, and a dedicated renderer consumes a shared globe-anchor projection helper.

### Phase 1 — authoritative data and compatibility

1. Extend `modules/base/systems/military/combat_system.py`’s battle schema and row builder with `anchor_latitude`, `anchor_longitude`, and `anchor_source`.
2. Add a small simulation-side anchor policy beside the military combat system. It computes a spherical mean of finite, in-range participant contact coordinates ordered by unit ID on first creation, otherwise uses the region center, then preserves the original values on every update.
3. Mirror the columns in `modules/base/schema.py`. Use nullable schema defaults only as a pre-normalization compatibility state; `src/server/state_migrations.py` must backfill legacy rows from their actual region latitude/longitude before schema capture. Never interpret `0,0` as “missing,” because it is a valid geographic location.
4. Extend state validation for finite coordinate ranges and the `contact`/`region_center` source vocabulary. Repair missing legacy anchors when their region exists; leave the client contract able to isolate a malformed incoming row without hiding other overlays.
5. Keep `mode`, status transitions, events, and battle IDs unchanged; add regression assertions that passive contact and assault escalation still use the current authoritative behavior and that stalemate lifecycle bookkeeping remains idempotent.

### Phase 1 — client projection and visual effects

1. Add a reusable geographic anchor projection helper containing the back-face test, projected silhouette clearance, and bounded screen-size calculation already proven by existing overlay math. Reject back-facing anchors. For a front-facing anchor, always draw the bounded static marker; draw halos, flashes, and exchange segments only when their complete footprint fits within the returned silhouette clearance. This avoids per-primitive circular clipping work while preserving battle visibility.
2. Keep `EventRenderer` and `UnitProjectionService` behavior unchanged in this feature. Verify projection parity with focused tests instead of expanding the change into unrelated overlay refactoring; later consumers may adopt the helper independently.
3. Add `src/client/renderers/battle_effect_renderer.py`. Cache normalized battle inputs, stable order, region lookup, and side palettes by relevant table revisions. Per frame, project only cached battle anchors, reject invisible anchors before phase/effect preparation, derive a pure phase with a stable byte-level digest of battle ID plus round/presentation time, and append all visible primitives to one no-input overlay draw list. Keep only a bounded short-lived conclusion cache; never use it to resurrect combat.
4. Move the existing unit-dependent battle marker out of `UnitRenderer` so filtered/hidden units do not suppress authoritative battle effects and duplicate markers are not drawn.
5. Integrate the renderer in `src/client/views/game_view.py` with `ClientGameClock.get_display_total_minutes()` and the local reduced-motion preference. Preserve input/selection/UI draw ordering and never mutate `GameState`.
6. Add Passive/Active label mapping in the military presenter/panel while retaining the raw `positional`/`assault` value for diagnostics.
7. Cache stable battle-ID ordering when battle revisions change. Each frame, insert visible bounded footprints into a screen-space grid whose cell size is at least the maximum bounded footprint diameter, then test collisions only within the same and neighboring cells, avoiding all-pairs overlap work without missing contacts. Assign the first available offset from a fixed ordered candidate set to labels and decorative effects. Keep a small leader and anchor mark at the authoritative point.

### Phase 1 — settings and validation

1. Add `reduce_motion` to the local game settings model, serialization, and settings UI with a default of `False`.
2. Implement focused tests for anchor policy, schema compatibility, globe projection and silhouette clearance, deterministic phases, revision-keyed caches, mode/lifecycle rendering, filtered units, reduced motion, grid-based overlap layout, and stalemate/conclusion idempotency.
3. Preserve the existing snapshot/presenter performance check and add `tests/test_battle_effect_performance.py` as a dedicated battle-effect preparation/render benchmark. Measure repeated baseline and 100-battle frames after warm-up and compare medians, then run the quickstart commands plus the defined globe orbit/zoom acceptance matrix.
4. Run the blinded Passive/Active classification protocol from the quickstart with at least 10 representative players and record the 200 classifications and aggregate result without collecting unrelated personal data.

## Project Structure

### Documentation (this feature)

```text
specs/106-tactical-battle-visualization/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── battle-visualization.md
├── checklists/
│   └── requirements.md
└── tasks.md                         # created later by $speckit-tasks
```

### Source Code (repository root)

```text
modules/base/
├── schema.py                         # additive battles schema/defaults
└── systems/military/
    ├── combat_system.py              # anchor fields and preservation
    └── battle_anchor_policy.py       # deterministic contact/region anchor mechanism

src/client/
├── renderers/
│   ├── globe_overlay_projection.py   # shared geo-to-screen/occlusion mechanism
│   ├── battle_effect_renderer.py     # passive/active aggregate effects
│   └── unit_renderer.py              # retain unit overlays; remove battle marker
├── services/
│   └── game_settings_service.py      # local reduced-motion preference
├── ui/
│   ├── components/settings_content.py
│   └── panels/military/               # Passive/Active status labels
└── views/game_view.py                 # renderer and presentation-clock integration

src/server/
├── state_migrations.py                # additive legacy normalization/validation
└── session.py                         # schema capture/ensure compatibility if required

tests/
├── test_battle_anchor_policy.py
├── test_globe_overlay_projection.py
├── test_battle_effect_renderer.py
├── test_battle_effect_performance.py
├── test_battle_status_interface.py
├── test_engagement_mvp.py             # regression for positional/assault modes
└── test_client_snapshot_performance.py
```

**Structure Decision**: Keep gameplay policy and authoritative table construction in the existing `modules/base` military system, reusable geometry in the client renderer layer, local preference in the client settings service, and validation in existing server/schema boundaries. No new engine loop, shared logic, or transport protocol is introduced.

## Complexity Tracking

No violations. The shared projection helper and dedicated effect renderer replace duplicated/visibility-coupled behavior rather than adding a parallel simulation or a new authoritative subsystem.
