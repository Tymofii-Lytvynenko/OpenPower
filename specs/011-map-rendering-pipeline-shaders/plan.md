# Implementation Plan: GPU Map Rendering Pipeline & Shader Registry

**Branch**: `011-map-rendering-pipeline-shaders` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-map-rendering-pipeline-shaders/spec.md`

## Summary

Close map-rendering gaps without changing the globe's current gameplay path: make the cached unique-index path validate source freshness and archive shape, preserve the input map's 2D shape across NumPy versions, close archive file handles, add a usable planar equirectangular renderer for the map editor, and provide the missing political-map shader bundle. Keep hover lookup a direct array access and preserve the existing 24-bit BGR encoding.

## Technical Context

**Language/Version**: Python 3.10+ (`pyproject.toml`); local `.venv` currently uses Python 3.14.1
**Primary Dependencies**: NumPy, OpenCV, Arcade/OpenGL 3.3, GLSL
**Storage**: Local cache `.npz` and `.npy` files under the existing project cache directory
**Testing**: pytest, synthetic PNG/cache tests, and optional hidden-window OpenGL shader compilation
**Target Platform**: Windows desktop with OpenGL 3.3; map decoding/indexing remains headless-safe
**Project Type**: Desktop grand-strategy game
**Performance Goals**: 60+ FPS at 4K for GPU map rendering; 1,000,000 region lookups/s (equivalent to <0.001 ms/query)
**Constraints**: Do not change the default globe or gameplay semantics; no display context for CPU map decoding/indexing; optimization limited to three measured iterations per algorithm
**Scale/Scope**: Existing globe renderer, reusable equirectangular map projection, cached dense region index, and editor-only planar map path

## Constitution Check

- **Layer separation**: Pass. OpenCV/NumPy packing stays in `src/core`; shader compilation stays in `src/client`.
- **Polars/data contracts**: Not applicable to pixel and texture arrays; existing region IDs remain unchanged.
- **Composition/SOLID**: Pass. The planar renderer is a composed projection component sharing the existing texture manager.
- **Commenting**: Pass. New comments explain orientation/caching rationale in English.
- **Empirical verification/anti-masking**: Pass after real archive tests, shader bundle tests, optional live GL compilation, and explicit performance-gate status.

## Project Structure

```text
src/core/map_data.py
src/core/map_indexer.py
src/core/cache_service.py
src/client/shader_registry.py
src/client/renderers/map_renderer.py
src/client/renderers/planar_map_renderer.py
src/client/renderers/shaders/political_map.vert
src/client/renderers/shaders/political_map.frag
src/client/ui/layouts/editor_layout.py
src/client/views/editor_view.py
tests/test_map_rendering_pipeline.py
specs/011-map-rendering-pipeline-shaders/
```

**Structure Decision**: Keep the existing globe implementation as the default. Add an independent planar projection component used by the editor's projection selector; it reuses `TextureManager` textures and data rather than duplicating asset/cache ownership. `ShaderRegistry` remains the single path and source-bundle entry point.

## Design Decisions

1. A valid map-index cache must be newer than its source and contain the current SHA-256 of that source. Recompute if either condition fails.
2. `CacheService.load_numpy_archive` returns copied arrays from a closed `np.load` context, and the indexer validates required keys and 2D shape before accepting a cache.
3. Reshape `np.unique(..., return_inverse=True)` output to the source grid explicitly; the public dense-index map shape is independent of NumPy-version behavior.
4. Add political-map shaders for flat equirectangular rendering and a composed `PlanarMapRenderer`; only the editor exposes the planar switch so gameplay units, battles, and globe input remain unchanged.
5. Performance measurements are gates, not open-ended tuning. Record baselines and stop after at most three implementation-measurement iterations per algorithm.

## Complexity Tracking

No constitution violations are introduced. Empirical 4K results are recorded in `performance-log.md`; they cover the production map-renderer paths but do not include full UI/scene composition.
