# Research: Unit Batch Renderer & Flag Atlas

## Decisions

### Keep GPU resources client-owned and disposable

- **Decision**: The atlas owns the single GPU texture and UV metadata; the batch renderer owns shader/buffer/geometry resources; unit projection remains separate and returns screen-space billboards.
- **Rationale**: This respects passive-client layering and keeps graphics-context lifetimes out of shared or simulation code.
- **Evidence**: `src/client/renderers/unit_flag_atlas.py`, `unit_batch_renderer.py`, and `unit_renderer.py` already follow this division.

### Use normalized UVs with transparent cell padding

- **Decision**: Preserve 32×22 RGBA flag interiors, a 2 px transparent border, bilinear GPU sampling, and Lanczos source downsampling. Rebuild only when an owner not yet packed appears; carry existing owners into the replacement atlas.
- **Rationale**: Padding isolates neighboring flags during linear filtering; owner-union rebuilds retain current in-view flags when mods add new countries.
- **Verification**: Existing tests inspect atlas mode/padding/fallback pixels, normalized UVs, and owner retention. Add sampling-edge and live GPU timing checks.

### Keep interaction visuals outside the flag batch

- **Decision**: Continue to render selected outlines, stack badges, movement routes, and drag/selection feedback through ImGui while normal flags use the GPU batch; send moves through `ActionMoveUnit`.
- **Rationale**: Dynamic UI state is sparse and should not force per-unit texture changes or couple input controllers to OpenGL.

## Empirical gate results

- `tests/test_unit_flag_atlas.py` retains the mocked 200-unit batch-call check and now has opt-in live OpenGL tests for dynamic owner uploads, driver-level timing, and linear-filter boundary sampling.
- Five new-owner updates on NVIDIA GeForce RTX 5060 Ti / OpenGL 4.6.0 (driver 591.74) measured 3.173, 3.371, 3.139, 4.728, and 3.734 ms; the 3.371 ms median meets the <15 ms target. The benchmark uses 200 existing flags, then adds five previously unseen owners with `glFinish()` inside each timed interval.
- GPU sampling across red/transparent/green cell boundaries returned `(191, 0, 0, 191)`, `(0, 0, 0, 0)`, and `(0, 191, 0, 191)`. A dynamically appended blue cell returned `(0, 0, 255, 255)` without changing existing texture ID or UV entries.
- Reserved atlas capacity and per-cell texture writes avoid re-decoding, re-packing, and re-uploading existing flags while free cells remain. Capacity growth still takes the full rebuild path so previously assigned UV slots remain stable.
