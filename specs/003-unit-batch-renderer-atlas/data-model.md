# Data Model: Unit Batch Renderer & Flag Atlas

This feature is presentation-only; no persistent tables are introduced.

## Runtime structures

| Structure | Key/data | Invariants |
|---|---|---|
| `FlagAtlasEntry` | owner tag → `(u0, v0, u1, v1)` and ImGui UV vectors | Frozen normalized coordinates; UV rectangle excludes 2 px padding and encloses the 32×22 flag interior. |
| `UnitFlagAtlas` | owner set, one RGBA GPU texture, entry map, fallback owner | Every requested owner resolves to its actual flag or default/magenta fallback; rebuilding retains all prior owner entries. |
| `ProjectedUnit` | unit ID/owner, globe projection, size, strength, stack metadata, movement/readiness | Immutable game snapshot projected to screen; does not mutate authoritative `GameState`. |
| `UnitBatchRenderer` | shader, dynamic vertex buffer/geometry, cached vertices | Six vertices per billboard; each vertex carries pixel position, atlas UV, and tint; one atlas texture is bound for the batch. |
| `UnitInteractionController` | selected/hovered IDs, drag state, map/network dependencies | Converts user selection and drag into semantic actions; never modifies simulation tables. |

## Frame flow

1. Read visible unit state and derive a stable units signature.
2. Ensure atlas coverage for all visible owners and any drag-preview owner.
3. Project units and calculate visual stack count/combined strength.
4. Build/reuse six-vertex billboards; bind the one flag atlas and submit one triangle draw for the normal batch.
5. Draw sparse ImGui overlays for routes, selected/hovered units, stack badges, drag preview, and selection rectangle.
6. The controller resolves the target region/coordinates and sends sorted `ActionMoveUnit` actions.

## Resource lifetime

GPU resources require a live Arcade context. CPU unit tests must fake upload and draw interfaces; context creation failure must leave the existing ImGui fallback available. Live performance and filtering are validated separately on a real context.
