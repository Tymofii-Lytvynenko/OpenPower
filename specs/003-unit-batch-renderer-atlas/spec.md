# Feature Specification: Interactive Unit Batch Renderer & Flag Atlas System

## User Scenarios & Testing

### Primary User Story
As a player viewing the global military map, I want military units and national flag icons packed into a single GPU texture atlas with billboard projection, stack clustering, and interactive mouse-drag selection controls, so that hundreds of units render smoothly without texture swapping bottlenecks.

### Acceptance Scenarios
1. **Flag Atlas Stitching**: **Given** active national flag icons in `assets/base/flags/`, **When** `UnitFlagAtlas._build_atlas` executes, **Then** all country flag textures are resized with Lanczos filter to 32x22 pixels, padded with 2px borders, and stitched into a single RGBA GPU texture.
2. **ImGui Draw List Insertion**: **Given** unit billboards rendered in ImGui UI layer, **When** `draw_flag()` is called, **Then** flag coordinates are referenced using normalized UV coordinates (`u0, v0` to `u1, v1`) from the single GPU texture ID (`self._texture_id`), eliminating per-flag GPU texture state switches.
3. **Unit Stack Clustering**: **Given** multiple units co-located within the same region or zoom radius, **When** zoomed out, **Then** units dynamically aggregate into visual stacks showing combined force strength numbers and nation ownership badges.
4. **Interactive Unit Selection & Routing**: **Given** a player selecting units via mouse click or drag box, **When** dragging to a target region, **Then** visual vector lines render from source to destination coordinates and an `ActionMoveUnit` is dispatched.

### Edge Cases
- Missing country flag PNG files: Automatically falls back to default `"XXX"` flag asset or magenta fallback image (`RGBA 255, 0, 255, 255`).
- Dynamic mod flag additions: `ensure_owners()` detects new country tags and rebuilds atlas on demand without dropping existing texture bindings.

## Exact Technical Specifications & Atlas Parameters

### Flag Atlas Configuration (`src/client/renderers/unit_flag_atlas.py`)
- **Cell Size**: 32 x 22 pixels (`FLAG_ATLAS_CELL_WIDTH = 32`, `FLAG_ATLAS_CELL_HEIGHT = 22`)
- **Cell Padding**: 2 pixels (`FLAG_ATLAS_PADDING = 2`)
- **Texture Format**: 4-component RGBA
- **GPU Sampling Filter**: `(ctx.LINEAR, ctx.LINEAR)`
- **Image Resampling Filter**: `Image.Resampling.LANCZOS`
- **Fallback Country Tag**: `"XXX"`
- **UV Coordinate Calculation**:
  \[ u0 = \frac{x}{\text{atlas\_w}}, \quad v0 = \frac{y}{\text{atlas\_h}}, \quad u1 = \frac{x + 32}{\text{atlas\_w}}, \quad v1 = \frac{y + 22}{\text{atlas\_h}} \]

## Key Data Structures

- **FlagAtlasEntry**: Immutable dataclass storing normalized UV bounding box `(u0, v0, u1, v1)` and ImGui vector helpers `uv_min` / `uv_max`.
- **UnitBillboardBatch**: Buffer storing screen projected coordinates, scale factors, selection state, and flag atlas UV lookups.

## Success Criteria

- **SC-001**: Single Draw Call Efficiency: 200+ unit flag icons on screen render within 1 GPU texture bind call.
- **SC-002**: Zero Texture Bleeding: 2px padding prevents neighboring flag pixels from leaking into icon edges during bilinear filtering.
- **SC-003**: Dynamic Atlas Expansion: Adding custom mod flags at runtime rebuilds GPU texture memory under 15ms.

## Assumptions & Dependencies

- **Assumption**: Pillow (PIL) manages image resizing (`ImageOps.contain`) and atlas stitching.
- **Dependency**: Arcade PyVideo OpenGL context (`ctx.texture`) allocates GPU texture ID (`glo`).
