# Feature Specification: GPU Map Rendering Pipeline & Shader Registry

## User Scenarios & Testing

### Primary User Story
As a grand strategy gamer, I want a high-performance GPU map rendering pipeline supporting 3D spherical globe and 2D planar map projections, 24-bit BGR region ID color packing, cached spatial map indexing, and custom GLSL shaders (`ShaderRegistry`), so that global geopolitical maps render smoothly with pixel-accurate hover detection.

### Acceptance Scenarios
1. **24-bit BGR Color Packing**: **Given** a regional map image (`regions.png`), **When** `RegionMapData` initializes via OpenCV (`cv2.imread`), **Then** pixels are packed into a 24-bit 2D integer array \(\text{packed\_map} = B \mid (G \ll 8) \mid (R \ll 16)\) and raw BGR channels are deleted to save RAM.
2. **Cached Unique ID Indexing**: **Given** map data arrays, **When** `MapIndexer.get_indices` executes, **Then** `np.unique(..., return_inverse=True)` builds spatial index maps cached to disk as SHA-256 verified `.npz` archives via `CacheService`.
3. **GLSL Shader Registry Bundle Loading**: **Given** shader bundle requests, **When** `ShaderRegistry.load_bundle()` runs, **Then** vertex and fragment GLSL files (`political_map.vert`/`frag`, `globe.vert`/`frag`) are read into string bundles for Arcade OpenGL shader compilation.
4. **Pixel-Accurate Hover Lookup**: **Given** mouse cursor coordinates \((x, y)\), **When** `get_region_id(x, y)` is called, **Then** the 24-bit region ID is returned in \(O(1)\) time.

### Edge Cases
- Missing GLSL shader files: FileNotFoundError caught with clear log.
- Headless execution: `RegionMapData` uses headless-safe OpenCV `cv2.imread()` without requiring a active windowing display context.
- Stale index cache: `CacheService.is_cache_valid` compares SHA-256 hashes and modification timestamps (`st_mtime`), auto-regenerating index archives if stale.

## Exact Technical Specifications & Code Contracts

### 1. 24-bit Color Packing Formula (`src/core/map_data.py`)
\[ \text{PackedID}(x, y) = B(x, y) \mathbin{\vert} (G(x, y) \ll 8) \mathbin{\vert} (R(x, y) \ll 16) \]

### 2. Shader Registry Bundle Paths (`src/client/shader_registry.py`)
- **Political View Shaders**:
  - Vertex Shader: `src/client/renderers/shaders/political_map.vert`
  - Fragment Shader: `src/client/renderers/shaders/political_map.frag`
- **Globe Sphere Shaders**:
  - Vertex Shader: `src/client/renderers/shaders/globe.vert`
  - Fragment Shader: `src/client/renderers/shaders/globe.frag`

### 3. Application Launcher & Multiprocessing (`main.py`)
- Multiprocessing Start Method: `mp.set_start_method('spawn', force=True)`
- Freeze Support: `mp.freeze_support()`
- Profiler Export: `pyinstrument.Profiler` HTML output saved to `profile_results.html`

## Success Criteria

- **SC-001**: High Framerate GPU Rendering: Global map renders at 60+ FPS at 4K resolution.
- **SC-002**: Direct O(1) Region Lookup: `get_region_id` evaluates in under 0.001ms per query.
- **SC-003**: Zero Memory Leakage: OpenCV raw BGR memory buffers deleted immediately after ID array packing.

## Assumptions & Dependencies

- **Assumption**: OpenCV (`cv2`) handles headless image decoding.
- **Dependency**: NumPy handles array indexing and `.npz` archive compression.
