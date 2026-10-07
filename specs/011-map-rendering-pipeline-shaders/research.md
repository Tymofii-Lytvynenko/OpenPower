# Research: GPU Map Rendering Pipeline & Shader Registry

## Existing implementation

- `RegionMapData` uses headless-safe `cv2.imread`, packs BGR pixels into signed 32-bit integer IDs with the specified formula, and deletes both split channels and the raw image. `get_region_id` is already a direct bounds-checked 2D lookup.
- `MapIndexer` already uses `np.unique(..., return_inverse=True)` and persists the source SHA-256 alongside unique IDs and dense indices. It currently skips `CacheService.is_cache_valid`, accepts any archive with a matching hash without shape checks, and relies on the installed NumPy's inverse-shape behavior.
- `CacheService.is_cache_valid` uses modification time. `load_numpy_archive` returns an open `NpzFile`, despite its `Dict` contract, and its handle lifetime is not closed by the indexer.
- `ShaderRegistry` defines globe shader paths and reads explicit bundle paths. Globe shaders exist; the required `political_map.vert` and `political_map.frag` are missing. Missing files naturally raise, but the message does not identify the bundle request clearly.
- `MapRenderer` currently renders a 3D globe. `EquirectangularProjection` and the country region-map rasterizer already provide planar coordinate/raster behavior. The editor has a `View` menu and is the safe place for a 2D global-map projection selector because the gameplay view layers globe-projected units and battles over the current globe.
- `main.py` already calls `mp.freeze_support()` and `mp.set_start_method("spawn", force=True)` under the executable guard and can export a PyInstrument HTML profile when enabled.

## Context7 API verification

Context7 documentation for `/pythonarcade/arcade` confirms `arcade.gl.geometry.quad_2d_fs()` supplies the `in_vert` and `in_uv` attributes, and `ctx.program(vertex_shader=..., fragment_shader=...)` compiles source strings. This supports a 2D shader component without introducing another rendering dependency.

Reference: [Arcade full-screen shader quad example](https://github.com/pythonarcade/arcade/blob/development/doc/tutorials/shader_inputs/index.rst).

## Decisions

- Use both cache freshness (mtime) and source SHA-256 verification; the hash remains the source-content authority.
- Treat missing keys, mismatched hash, or wrong index shape as a cache miss. Do not silently return malformed arrays.
- Keep map ID packing and hover lookup code paths unchanged unless a test reveals a correctness issue.
- Implement planar map rendering as an editor-only composed projection that shares the existing cached textures and lookup table; leave gameplay's default globe and its overlays alone.
- Use a real optional OpenGL test for shader compilation/rendering; headless tests verify source loading and CPU coordinate transforms.
