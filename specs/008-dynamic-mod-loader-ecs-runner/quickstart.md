# Quickstart: Dynamic Mod Loader and ECS Runner

## Focused checks

```powershell
.venv\Scripts\python.exe -m pytest `
  tests/test_mod_manager.py tests/test_mod_api.py `
  tests/test_engine_determinism.py tests/test_layer_boundaries.py -q
```

This covers manifest dependency expansion/errors, current and legacy registration entry points, warning-and-skip behavior, higher-priority overrides, deterministic order, and cycle diagnostics.

## Cold startup gate

```powershell
$env:RUN_MOD_STARTUP_BENCHMARKS = "1"
.venv\Scripts\python.exe -m pytest tests/test_mod_startup_performance.py -q -s -p no:cacheprovider
```

Latest cold local result on Python 3.14.1: **179.678 ms**, one active mod and 30 registered systems; SC-003 passed.

## Full-suite boundary

Latest full repository regression: **684 passed, 16 skipped, 116 warnings, 190 subtests passed in 162.89 seconds**. The warnings are upstream pyglet/Windows ctypes deprecations; no test failed. Opt-in performance workloads are run separately with their documented environment flags.
