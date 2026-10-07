# Quickstart and Verification

## Headless checks

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_map_rendering_pipeline.py
```

This exercises BGR packing, bounds handling, dense-index shape, SHA/mtime invalidation, planar pixel mapping, and shader source resolution without creating a display context.

## Optional OpenGL check

```powershell
$env:RUN_MAP_RENDERER_GPU_CHECKS = '1'
.venv\Scripts\python.exe -m pytest -q tests/test_map_rendering_pipeline.py -k live
```

The hidden-window test reports GL vendor/renderer/version and verifies shader compilation and representative pixels. It does not claim 60 FPS at 4K; record that separately from a live map session.

## Optional 4K renderer benchmark

```powershell
$env:RUN_MAP_RENDERER_PERFORMANCE_CHECKS = '1'
.venv\Scripts\python.exe -m pytest -s -q tests/test_map_rendering_pipeline.py::test_live_globe_and_planar_map_renderers_meet_4k_frame_budget
```

This loads the production map/terrain textures and measures the globe and planar map-renderer paths in a hidden 3840×2160 OpenGL window. Cache writes are redirected to pytest's temporary directory and disabled for the measurement. The result excludes UI composition and other scene layers, so it is not a full-application frame-time guarantee.

## Performance gates

- Map lookup target: <0.001 ms/query. Measure at least 100,000 lookups after warmup and record median/p95.
- GPU map target: 60+ FPS at 3840x2160 with the production map and driver's normal settings. Record GPU/driver, map size, overlay mode, and sample duration.
- Do not tune an algorithm without a baseline. Maximum three measured optimization iterations per algorithm; if the target remains unmet, record each attempt and result in `performance-log.md`, stop tuning, and continue with other specifications.
