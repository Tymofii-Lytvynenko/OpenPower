# Quickstart: Treaty and Diplomatic Map Overlay

## Focused verification

```powershell
.venv\Scripts\python.exe -m pytest `
  tests/test_data_loader_mod_layering.py `
  tests/test_treaty_specification.py tests/test_treaty_rules.py `
  tests/test_empire_map_mode.py tests/test_political_map_mode.py `
  tests/test_viewport_map_refresh.py tests/test_map_rendering_pipeline.py -q
```

This checks base treaty/war parsing, diplomacy color states, active/suspended/expired behavior, occupation and focus cache invalidation, shader source contracts, and CPU-testable LUT interpolation.

## Controlled color recalculation gate

```powershell
$env:RUN_EMPIRE_MAP_BENCHMARKS = "1"
.venv\Scripts\python.exe -m pytest tests/test_empire_map_mode_performance.py -q -s -p no:cacheprovider
```

The fixture has 4,559 regions and alternates focus between two countries. Latest 12-thread run: **0.792 ms median** after five warmups and 31 samples.

Focused loader, treaty, map-mode, viewport, renderer, time, population, and schema regressions: **39 passed** (2026-10-07).

Latest complete repository suite after the static war-table, diplomacy-color, renderer, and cross-system changes: **684 passed, 16 skipped, 116 warnings, 190 subtests passed in 162.89 seconds** (2026-10-07).

## Live GPU shader check

```powershell
$env:RUN_MAP_RENDERER_GPU_CHECKS = "1"
.venv\Scripts\python.exe -m pytest -q -s -p no:cacheprovider `
  tests/test_map_rendering_pipeline.py::test_live_globe_shader_compiles_and_renders_transition_borders_and_selection
```

On NVIDIA GeForce RTX 5060 Ti / OpenGL 4.6.0 NVIDIA 591.74, the shader compiled and the framebuffer check confirmed the prior/midpoint/target palette samples, border darkening, and selection tint. This does not exercise the application scene or input dispatch.

## Manual client confirmation

Run the desktop client, switch between Political and Empire modes, alternate country focus during the 250 ms palette blend, and inspect globe seams and selected-region outlines. Click regions to verify focus/picking. The actual on-screen visual and interaction check remains open; it is not inferred from framebuffer tests.
