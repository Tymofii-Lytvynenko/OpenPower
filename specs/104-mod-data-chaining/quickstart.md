# Quickstart: Mod Data Chaining

Run focused correctness checks from the repository root:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_mod_manager.py tests/test_game_config.py tests/test_data_loader_mod_layering.py tests/test_mod_startup_performance.py
```

The tests cover dependency ordering/cycles/missing prerequisites, engine/API compatibility, keyed region/country/world overlays, asset and localization precedence, and ordered runtime contributions.

Run the opt-in 25-mod chain benchmark separately from other large workloads:

```powershell
$env:POLARS_MAX_THREADS = '1'
$env:RUN_MOD_CHAIN_BENCHMARKS = '1'
.venv\Scripts\python.exe -m pytest -s -q tests/test_mod_data_chaining_performance.py
```

The gate is a median below 1.5 seconds after warm-up. Fixture construction is outside the measured interval. Record the runtime, thread count, sample count, and merge workload; do not tune a passing result.
