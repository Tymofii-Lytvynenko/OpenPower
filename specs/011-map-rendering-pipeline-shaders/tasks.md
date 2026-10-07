# Tasks: GPU Map Rendering Pipeline & Shader Registry

**Input**: Design documents in `specs/011-map-rendering-pipeline-shaders/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`

## Phase 1: CPU map data and lookup (US1)

**Goal**: Preserve the specified 24-bit BGR IDs, release raw buffers, and keep hover lookup O(1).

- [X] T001 [US1] Extend `tests/test_map_rendering_pipeline.py` for dtype, retained-memory contract, bounds, and a lookup timing baseline.
- [X] T002 [US1] Verify the CPU map-data contract in `src/core/map_data.py`; retain the direct array lookup because the existing implementation already satisfied it.

## Phase 2: Verified dense-index cache (US2)

**Goal**: Validate cache freshness, hash, required archive members, and index shape across NumPy versions.

- [X] T003 [US2] Add real `CacheService` archive lifecycle and invalidation tests in `tests/test_map_rendering_pipeline.py`.
- [X] T004 [US2] Return copied archive arrays after closing `np.load`; save archives atomically in `src/core/cache_service.py`.
- [X] T005 [US2] Validate mtime, SHA-256, required keys, and source shape; reshape `return_inverse` to the source map in `src/core/map_indexer.py`.

## Phase 3: Shader bundles and planar editor view (US3)

**Goal**: Load/compile all required shader pairs and make the planar equirectangular projection selectable in the map editor.

- [X] T006 [US3] Add path-specific missing-shader diagnostics and verify all four shader paths in `src/client/shader_registry.py` and `tests/test_map_rendering_pipeline.py`.
- [X] T007 [US3] Add `political_map.vert` and `political_map.frag` in `src/client/renderers/shaders/`.
- [X] T008 [US3] Add a composed planar renderer sharing existing textures in `src/client/renderers/planar_map_renderer.py` and integrate the projection mode in `src/client/renderers/map_renderer.py`.
- [X] T009 [US3] Add editor projection selection and same-transform hover/pan/zoom behavior in `src/client/ui/layouts/editor_layout.py`, `src/client/views/editor_view.py`, and `src/client/controllers/viewport_controller.py`.
- [X] T010 [US3] Test planar letterbox/zoom/pan pixel mapping headlessly; compile and render both shader programs in the optional hidden-window GPU check in `tests/test_map_rendering_pipeline.py`.

## Phase 4: Launcher contract and empirical gates (US4)

- [X] T011 [US4] Verify spawn start method, freeze support, and optional profiler export behavior in `tests/test_main_profiling.py`.
- [X] T012 Run focused map tests and record lookup median/p95 and hardware in `performance-log.md`.
- [X] T013 Measure 4K globe/planar rendering at 60+ FPS on a live GPU; document the measured results and any optimization iterations in `performance-log.md`.

## Dependencies and execution order

- T001–T002 preserve the CPU contract and are independent of GL rendering.
- T003–T005 precede renderer texture upload, which depends on 2D dense-map indices.
- T006–T010 share shader contracts; the headless transform tests do not require a GPU.
- T012 follows the focused test suite; T013 requires a desktop OpenGL session.

## Performance iteration policy

Record a baseline before tuning each algorithm. Allow at most three measured optimization iterations. If a gate still fails after iteration three, record all attempts/results in `performance-log.md`, stop tuning, and continue with remaining specifications.
