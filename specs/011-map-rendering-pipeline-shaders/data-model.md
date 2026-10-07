# Data Model: Map Rendering Pipeline

No persistent game-state schema changes are introduced.

## Region pixels and indices

- `RegionMapData.packed_map` is an `int32` array shaped `(height, width)`.
- Pixel IDs use OpenCV BGR channel order: `B | (G << 8) | (R << 16)`.
- `MapIndexer.get_indices` returns `unique_ids` as a 1D vector and `dense_map` with the same 2D shape as `packed_map`.
- Cache archive keys are `unique_ids`, `dense_map`, and `hash`; `hash` is the source file SHA-256 string.

## GPU textures

- Map visualization texture encodes dense IDs into RGB and the precomputed region border mask into alpha.
- Lookup textures store current and previous country colors; the existing transition uniform blends them.
- The planar projection uses the same texture manager and lookup semantics as the globe, but maps the full equirectangular image to an aspect-preserving screen quad.

## Cache validity

An index archive is usable only when its cache file is newer than the source, its embedded SHA-256 matches the current source, required arrays are present, and the dense index grid shape matches the source image. Any failed check triggers a deterministic rebuild.
