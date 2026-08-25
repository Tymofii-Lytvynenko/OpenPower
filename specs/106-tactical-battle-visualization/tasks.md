---

description: "Implementation tasks for tactical battle visualization"
---

# Tasks: Tactical Battle Visualization

**Input**: Design documents from `/specs/106-tactical-battle-visualization/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), and [contracts/battle-visualization.md](contracts/battle-visualization.md)

**Tests**: Required by FR-018 and the success criteria. Write focused tests before the corresponding story implementation and keep the existing combat, clock, and layer-boundary tests green.

**Organization**: There is one prioritized user story in the specification. The story phase contains the complete independently testable MVP; foundational tasks only establish shared schema, migration, projection, and settings boundaries.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish deterministic fixtures and a repeatable baseline before changing authoritative or client code.

- [ ] T001 [P] Create deterministic Polars fixture builders for battle, unit, region, camera, and presentation-clock inputs in `tests/test_battle_visual_fixtures.py`
- [ ] T002 [P] Verify and maintain the focused test command, finite globe-camera matrix, blinded Passive/Active UAT protocol, and baseline-versus-feature measurement procedure in `specs/106-tactical-battle-visualization/quickstart.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish additive contracts that every battle-visualization path relies on.

**⚠️ CRITICAL**: No user story implementation begins until this phase is complete.

- [ ] T003 Register `anchor_latitude`, `anchor_longitude`, and `anchor_source` in `modules/base/systems/military/combat_system.py` and `modules/base/schema.py`, permitting null only before migration and never treating the valid coordinate `0,0` as a missing-value sentinel
- [ ] T004 Extend `src/server/state_migrations.py` and `src/server/session.py` to backfill missing/null legacy anchors from the referenced region before schema capture, validate finite coordinate/source values, and preserve old saves plus generic snapshot compatibility
- [ ] T005 [P] Define `ProjectedSurfacePoint` with front/back visibility, screen position, bounded marker size, and silhouette clearance in `src/client/renderers/globe_overlay_projection.py` without importing gameplay or server modules
- [ ] T006 [P] Add the local `reduce_motion` setting field, default, and load/save compatibility in `src/client/services/game_settings_service.py`

**Checkpoint**: The additive battle schema, legacy handling, shared projection boundary, and local presentation setting are available without changing combat outcomes.

---

## Phase 3: User Story 1 - Locate and distinguish battles on the globe (Priority: P1) 🎯 MVP

**Goal**: Show every authoritative battle at a stable geographic anchor, distinguish passive contact from active assault with deterministic smooth effects, and keep the display correct through camera motion, filtering, lifecycle changes, allies, and reduced motion.

**Independent Test**: Run the focused pytest command in `specs/106-tactical-battle-visualization/quickstart.md`, then perform its manual globe scenario. A passing increment keeps the same battle ID/anchor across `positional` → `assault`, hides back-facing effects, shows markers without visible units, stops concluded effects, and keeps the 100-battle budget.

### Tests for User Story 1 (write first and verify they fail for missing behavior)

- [ ] T007 [P] [US1] Add spherical contact-anchor, longitude-seam, actual region-coordinate backfill, nullable pre-migration, valid `0,0`, and anchor-preservation tests in `tests/test_battle_anchor_policy.py`
- [ ] T008 [P] [US1] Add projection tests for yaw at 45-degree intervals, pitch at `-60/-30/0/30/60`, minimum/midpoint/maximum zoom, both longitude-seam sides, back-face rejection, front-facing marker retention, decorative-footprint culling by silhouette clearance, parity with existing overlay projection, and bounded screen size in `tests/test_globe_overlay_projection.py`
- [ ] T009 [P] [US1] Add renderer contract tests for Passive/Active patterns, stable-digest phases/colors/order, revision-keyed cache invalidation, maximum-footprint-sized grid-neighbor collision checks and fixed-candidate offsets with exact anchor leaders, filtered-unit visibility, malformed-row fallback, reduced motion, stalemate, one-second conclusion expiry, and a single no-input draw overlay in `tests/test_battle_effect_renderer.py`
- [ ] T010 [P] [US1] Extend authoritative regression coverage for anchor creation, unchanged battle ID on assault escalation, mode/status terminology, allied side identity, replay stability, and stalemate idempotency in `tests/test_combat_system.py`, `tests/test_engagement_mvp.py`, `tests/test_battle_status_interface.py`, `tests/test_battle_allies.py`, and `tests/test_tactical_combat_replay.py`
- [ ] T011 [P] [US1] Create `tests/test_battle_effect_performance.py` with warmed-up repeated baseline and 100-battle renderer samples, median overhead calculation, the five-percent gate, bounded battle-count work, and no unit-billboard dependency while preserving `tests/test_client_snapshot_performance.py` as a separate transport regression

### Implementation for User Story 1

- [ ] T012 [US1] Implement the pure spherical-mean/contact-or-region fallback policy with coordinate/source validation in `modules/base/systems/military/battle_anchor_policy.py`
- [ ] T013 [US1] Integrate first-contact anchor construction and prior-row anchor preservation into `_build_battle_row` and battle update flow in `modules/base/systems/military/combat_system.py`, while retaining existing mode, ID, outcome, and side rules
- [ ] T014 [US1] Implement geographic-to-screen projection, back-face rejection, front-facing silhouette clearance, seam safety, and bounded marker sizing in `src/client/renderers/globe_overlay_projection.py`, proving parity through tests without modifying `src/client/renderers/event_renderer.py` or `src/client/renderers/unit_projection.py`
- [ ] T015 [US1] Implement `BattleEffectRenderer` in `src/client/renderers/battle_effect_renderer.py` using cached normalized battles, stable order, region lookup, and side palettes keyed by table revisions; per frame project visible candidates only, cull decorative limb geometry, derive stable-digest phases, use a collision grid sized to the maximum bounded footprint with neighbor-only checks, fixed offsets, and exact anchor leaders, bound the conclusion cache, and rate-limit malformed-row diagnostics
- [ ] T016 [US1] Remove the visible-unit-dependent battle marker from `src/client/renderers/unit_renderer.py` and integrate one independent no-input battle overlay in `src/client/views/game_view.py` with `get_display_total_minutes()`, camera ordering, and the local reduced-motion setting
- [ ] T017 [P] [US1] Add a reduced-motion control and persistence binding in `src/client/ui/components/settings_content.py` and `src/client/ui/panels/service/settings_panel.py`, preserving the static marker/state-label behavior
- [ ] T018 [P] [US1] Add one shared Passive/Active display mapping, raw canonical mode text, and lifecycle labels to `src/client/ui/panels/military/presenter.py` and `src/client/ui/panels/military/battle_overview_panel.py`
- [ ] T019 [US1] Add integration assertions that the map renderer and battle status panel use the same mode mapping and that client rendering never dispatches gameplay actions in `tests/test_battle_status_interface.py` and `tests/test_layer_boundaries.py`
- [ ] T020 [US1] Run the focused contract, combat, projection, renderer, and performance tests from `specs/106-tactical-battle-visualization/quickstart.md`, resolve regressions without weakening assertions, and record observed results in that guide
- [ ] T021 [US1] Execute the finite yaw/pitch/zoom/seam globe matrix plus unit-filter, passive-to-active, stalemate/conclusion, overlap, and reduced-motion acceptance scenarios in `specs/106-tactical-battle-visualization/quickstart.md` and record the results
- [ ] T022 [US1] Run the blinded 10-participant, 20-display Passive/Active classification protocol from `specs/106-tactical-battle-visualization/quickstart.md`, record at least 200 anonymous judgments, and verify at least 190 are correct

**Checkpoint**: User Story 1 is independently demonstrable and satisfies the MVP acceptance scenarios without modifying combat calculations or authoritative outcomes.

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Verify integration quality, performance, and documentation after the MVP is complete.

- [ ] T023 [P] Reconcile implementation details, fallback vocabulary, marker-retention/decorative-culling semantics, grid-based overlap layout, cache invalidation, and file references across `specs/106-tactical-battle-visualization/spec.md`, `specs/106-tactical-battle-visualization/data-model.md`, and `specs/106-tactical-battle-visualization/contracts/battle-visualization.md`
- [ ] T024 [P] Run the full relevant regression set, including `tests/test_combat_system.py`, `tests/test_engagement_mvp.py`, `tests/test_battle_allies.py`, `tests/test_battle_status_interface.py`, `tests/test_client_game_clock.py`, `tests/test_client_snapshot_performance.py`, `tests/test_battle_effect_performance.py`, and `tests/test_layer_boundaries.py`
- [ ] T025 Verify the 100-battle median frame-time target in `tests/test_battle_effect_performance.py` and inspect `src/client/renderers/battle_effect_renderer.py` for per-unit work, repeated Polars conversion, unnecessary sorting, all-pairs collision checks, and avoidable per-frame allocations; keep snapshot transport measurements separate
- [ ] T026 Run the complete validation flow in `specs/106-tactical-battle-visualization/quickstart.md` and record automated, globe-matrix, UAT, and final empirical results before declaring the feature complete

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 and T002 are independent and can run immediately.
- **Foundational (Phase 2)**: T003 must land before T004; T005 and T006 can proceed in parallel with T003/T004. All foundational tasks block the story phase.
- **User Story 1 (Phase 3)**: T007–T011 can be written in parallel after the foundation; implementation starts with T012, T013, and T014, then T015, then T016. T017 depends only on T006; T018 can proceed from the existing presenter contract. T019–T022 run after the integrated renderer and UI are available.
- **Polish (Phase 4)**: T023–T026 depend on the MVP checkpoint and cover the whole feature.

### User Story Dependencies

- **User Story 1 (P1)**: Depends only on Phases 1–2. There are no additional story dependencies because the specification contains one primary story.

### Within User Story 1

- Tests T007–T011 are intentionally created before T012–T019 and should fail for the unimplemented behavior.
- T012 produces the reusable anchor policy; T013 makes it authoritative and persistent.
- T014 produces the shared projection used by T015; T015 produces the renderer used by T016.
- T017 depends on T006 and is otherwise independent of anchor/projection work; T018 depends only on the existing battle status contract.
- T020–T022 are the story’s executable automated, visual, and user-acceptance validation gates.

## Parallel Execution Examples

### Setup and foundation

```text
Task T001: Build deterministic battle-visual test fixtures in tests/test_battle_visual_fixtures.py
Task T002: Record the baseline validation flow in specs/106-tactical-battle-visualization/quickstart.md

After T003 is ready:
Task T005: Define the globe projection boundary in src/client/renderers/globe_overlay_projection.py
Task T006: Add reduce_motion persistence in src/client/services/game_settings_service.py
```

### User Story 1 tests

```text
Task T007: Anchor policy tests in tests/test_battle_anchor_policy.py
Task T008: Projection tests in tests/test_globe_overlay_projection.py
Task T009: Renderer contract tests in tests/test_battle_effect_renderer.py
Task T010: Authoritative mode/side/replay regressions in tests/test_combat_system.py and related tests
Task T011: Dedicated 100-battle render benchmark in tests/test_battle_effect_performance.py
```

### User Story 1 implementation

```text
Task T012: Anchor policy in modules/base/systems/military/battle_anchor_policy.py
Task T014: Shared projection implementation in src/client/renderers/globe_overlay_projection.py

After T006:
Task T017: Reduced-motion control in src/client/ui/components/settings_content.py

Independently against the existing presenter contract:
Task T018: Passive/Active status mapping in src/client/ui/panels/military/
```

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete T001–T006 to establish compatible schemas, migrations, projection boundary, settings field, and deterministic fixtures.
2. Write T007–T011 and confirm the new tests fail for the missing behavior.
3. Implement T012–T019 in dependency order.
4. Stop at T020–T022 and validate the complete MVP independently before broader cleanup.

### Incremental Delivery

1. Deliver authoritative stable anchors and schema compatibility (T003, T004, T012, T013).
2. Deliver map projection and a static battle marker independent of unit filters (T005, T014, T015, T016).
3. Add Passive/Active intensity, lifecycle effects, side identity, and reduced motion (T015, T017, T018).
4. Complete performance, regression, manual, and user-acceptance validation (T019–T026).

### Scope Guardrails

- Do not add terrain, supply, new combat sides, projectile simulation, sound, camera shake, or combat-formula changes.
- Do not make the client write `GameState`, infer battle mode from visible units, or use network arrival time/randomness for animation.
- Preserve existing battle IDs, snapshot transport, and server-authoritative lifecycle/outcome behavior.

## Notes

- Every task uses the required `- [ ] T###` checklist format; `[P]` appears only where files can be changed independently, and `[US1]` appears only in the user-story phase.
- All implementation tasks name concrete repository paths so they can be executed without additional design context.
- The MVP is the complete P1 story because no lower-priority user stories were specified.
