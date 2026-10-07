# Quickstart: Unit Atlas and Batch Rendering

Run the renderer, atlas, clustering, route, and movement-controller tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_unit_flag_atlas.py tests/test_unit_stack_clustering.py tests/test_unit_route_overlay.py tests/test_military_movement_spec.py
```

The mocked 200-unit test checks one atlas bind call and one GPU geometry submission. It does not measure actual driver execution. For acceptance of the <15 ms new-owner atlas-update gate, add a previously unseen owner in a live graphics context and sample linear-filtered texels around neighboring cell edges; record timing and hardware/driver.

The live OpenGL checks are opt-in and run against the current GPU/driver without displaying a desktop window:

```powershell
$env:RUN_UNIT_ATLAS_GPU_CHECKS = "1"
.\.venv\Scripts\python.exe -m pytest -q -s tests/test_unit_flag_atlas.py
```

Latest controlled result (2026-10-07): NVIDIA GeForce RTX 5060 Ti, OpenGL 4.6.0 / driver 591.74. Five new-owner atlas updates measured 3.173, 3.371, 3.139, 4.728, and 3.734 ms (3.371 ms median, below the 15 ms gate). GPU linear-filter samples returned red `(191, 0, 0, 191)`, transparent padding `(0, 0, 0, 0)`, green `(0, 191, 0, 191)`, and the partially uploaded blue cell `(0, 0, 255, 255)`; no neighboring color crossed the transparent gap.
