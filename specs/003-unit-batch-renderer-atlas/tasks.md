# Tasks: Interactive Unit Batch Renderer & Flag Atlas

**Input**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/unit-rendering.md`

**Tests**: Required for atlas layout, batch submission, interaction dispatch, and failure fallback.

## Phase 1: Atlas and batch rendering

- [X] T001 [US1] Pack resized country flags into RGBA atlas cells with 32×22 interiors and 2 px transparent padding in `src/client/renderers/unit_flag_atlas.py`.
- [X] T002 [US1] Use normalized interior UVs and one atlas texture for batch submission in `src/client/renderers/unit_batch_renderer.py` and `src/client/renderers/unit_flag_atlas.py`.
- [X] T003 [P] [US1] Cover RGBA/padding, Lanczos resampler selection, missing-flag fallback, dynamic owner-union rebuild, normalized UV calls, and 200-icon bind/draw call counts in `tests/test_unit_flag_atlas.py`.
- [X] T004 [US1] Add an opt-in live-context benchmark for new-owner atlas rebuild and prove the <15 ms target with hardware/driver recorded in `tests/test_unit_flag_atlas.py`; median was 3.371 ms (samples 3.173, 3.371, 3.139, 4.728, 3.734 ms) on NVIDIA GeForce RTX 5060 Ti, OpenGL 4.6.0 / driver 591.74.
- [X] T005 [US1] Verify linear-filtered atlas cell boundaries have no visible adjacent-flag bleed in a live GPU sampling check; edge samples were red (191, 0, 0, 191), transparent gap (0, 0, 0, 0), and green (0, 191, 0, 191); a partially uploaded blue cell sampled as (0, 0, 255, 255).

## Phase 2: Clustering and interaction

- [X] T006 [US2] Project and cluster nearby billboards with combined strength/count and owner flag UVs in `src/client/renderers/unit_projection.py` and `src/client/renderers/unit_renderer.py`.
- [X] T007 [P] [US2] Verify stack membership/badges and owner-specific UV selection in `tests/test_unit_stack_clustering.py`.
- [X] T008 [US3] Implement click/drag, rectangle selection, route overlays, and semantic move-action dispatch in `src/client/controllers/unit_interaction_controller.py` and `src/client/renderers/unit_renderer.py`.
- [X] T009 [P] [US3] Add direct controller tests for left-click, drag preview, normalized box selection, sorted multi-unit `ActionMoveUnit` dispatch, and invalid target handling in `tests/test_unit_interaction_controller.py`.
- [X] T010 [P] [US3] Cover projected movement routes and route-cache invalidation in `tests/test_unit_route_overlay.py`.

## Phase 3: Final integration

- [X] T011 [US1] Preserve the ImGui draw path when batch GPU rendering is unavailable in `src/client/renderers/unit_renderer.py` and renderer tests.
- [X] T012 Run atlas, batch, stack, route, and controller tests after T009; focused matrix result is 27 passed, 2 opt-in GPU checks skipped by default, 3 subtests passed. The separate live GPU run passed both checks on NVIDIA GeForce RTX 5060 Ti / OpenGL 4.6.0.

## Dependencies & Execution Order

- T001 precedes UV/batch integration and test tasks T002–T003.
- Clustering and interaction can be tested independently after projection/controller paths are in place.
- T012 depends on all automated tasks; empirical T004–T005 require a real graphics context and are recorded only from the separate live GPU run.
- All tasks are complete. The opt-in GPU checks are skipped in routine headless runs because their live-context results are recorded separately above.
