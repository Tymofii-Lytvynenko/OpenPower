# Implementation Plan: Interactive Unit Batch Renderer & Flag Atlas

**Branch**: `003-unit-batch-renderer-atlas` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification at `specs/003-unit-batch-renderer-atlas/spec.md`

## Summary

Render projected unit flags from one owner-aware atlas and one dynamic GPU batch, while preserving the existing ImGui overlay for selection, movement routes, stack badges, and interaction feedback. Keep CPU projection/clustering and rendering as composable client services; dispatch movement intent through the existing semantic action/network boundary.

## Technical Context

**Language/Version**: Python (repository runtime in `pyproject.toml`)

**Primary Dependencies**: Arcade/OpenGL context, `imgui_bundle`, Pillow, NumPy.

**Storage**: Runtime GPU atlas and CPU projected-billboard buffers; no persistent game-state changes.

**Testing**: pytest with mocked GPU context/draw calls and client controller fakes; empirical performance checks on a live graphics context.

**Target Platform**: Existing OpenPower desktop client with Arcade and ImGui.

**Project Type**: Python desktop game client.

**Performance Goals**: One atlas bind and one batch draw for 200+ normal billboards; dynamic atlas rebuild below 15 ms; no regression to responsive frame pacing.

**Constraints**: No direct `GameState` writes from client; preserve renderer fallback if GPU setup fails; keep atlas entries normalized; retain interactive overlays independently of the batch path; do not require a graphics context for unit tests.

**Scale/Scope**: Active owner flags, hundreds of projected units, screen-space stacks, selected-unit routes, selection rectangles, and drag-to-move interaction.

## Constitution Check

**Before research**

- Layering/passive client: PASS — presentation reads projected state and sends `ActionMoveUnit`; no simulation policy enters the client.
- Modularity/SOLID: PASS — atlas, batch renderer, projection, interaction controller, and draw overlays have separate responsibilities.
- Data/persistence contracts: PASS — rendering-only feature; no authoritative world schema changes.
- Empirical verification: PASS WITH OPEN GATES — mocked tests cover layout and draw submission; live GPU sampling and <15 ms atlas expansion still need a reproducible run.

**After design**: no new dependency or cross-layer edge is proposed. Live graphics behavior must still be observed on the target driver.

## Design and Research

See [research.md](research.md), [data-model.md](data-model.md), [contracts/unit-rendering.md](contracts/unit-rendering.md), and [quickstart.md](quickstart.md).

### Implementation locations

```text
src/client/renderers/
├── unit_flag_atlas.py             # Resize, pack, upload, and map owner flags to UVs
├── unit_batch_renderer.py         # Vertex buffer/shader and single atlas draw
├── unit_projection.py             # Globe-to-screen projections and clustering
└── unit_renderer.py               # Compose batch with ImGui overlays/routes/badges

src/client/controllers/unit_interaction_controller.py  # Selection and action dispatch
src/client/views/game_view.py                         # Per-frame renderer integration
tests/test_unit_flag_atlas.py
tests/test_unit_stack_clustering.py
tests/test_unit_route_overlay.py
```

**Structure Decision**: Extend the existing client renderers/controller and their tests; no new top-level package or engine interface is needed.

## Complexity Tracking

No constitution exception is approved. The GPU-specific performance target remains an empirical gate, separate from mocked call-count tests.
