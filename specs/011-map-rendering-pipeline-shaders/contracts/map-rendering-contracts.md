# Map Rendering Contracts

## CPU map data

- `RegionMapData` decodes without a window/display context.
- `packed_map[y, x]` is the 24-bit ID from the BGR source pixel; no decoded BGR buffer remains retained after construction.
- Out-of-bounds lookups return `0`; in-bounds lookups return the stored integer directly.

## Index cache

- A valid `.npz` contains the current source SHA-256, 1D unique IDs, and a 2D dense map matching the source map's shape.
- Cache mtime staleness or SHA mismatch triggers recomputation.
- Corrupt/malformed cache data is treated as a cache miss with a diagnostic; archive handles are closed before return.

## Shader bundles

- `ShaderRegistry.POLITICAL_V/POLITICAL_F` and `GLOBE_V/GLOBE_F` resolve to existing GLSL files.
- `load_bundle` returns UTF-8 `vertex_shader` and `fragment_shader` source strings.
- Missing shader sources produce a path-specific `FileNotFoundError` and a logged diagnostic.

## Projection modes

- The globe remains the default renderer and gameplay surface.
- The map editor can select the planar equirectangular projection; viewport picking uses the exact same letterbox, zoom, and map-center transform as the shader.
