# Quickstart: Internal Economy, Budget & Trade

## Correctness tests

Run the specification and nearby integration tests from the repository root:

```powershell
python -m pytest tests/test_economy_specification.py tests/test_treaty_trade_policy.py
```

Run the full suite before merging broad economy changes:

```powershell
python -m pytest
```

Latest full-suite verification after the economy, demographic vectorization, runtime, diplomacy, and AI benchmark changes: 684 passed, 16 skipped, 116 warnings, and 190 subtests passed in 162.89 seconds. The warnings are pyglet/Windows `ctypes._pointer_type_cache` deprecations; they did not fail tests.

## Performance gate

Run the opt-in economy benchmark with a controlled Polars thread count:

```powershell
$env:POLARS_MAX_THREADS = "1"
$env:RUN_ECONOMY_BENCHMARKS = "1"
.\.venv\Scripts\python.exe -m pytest -q -s tests/test_economy_performance.py
```

Record hardware/runtime, warm-up policy, per-system and combined timings, and fixture size. Acceptance requires the combined 200+ nation tick to be below 5 ms and parity tests to pass. After three bounded optimization iterations, the latest controlled run measured 8.22 ms (3.48 ms trade, 3.40 ms economy, 1.33 ms budget); two same-revision runs measured 8.44 ms and 8.54 ms. The gate remains open and is deferred to a future optimization pass. Earlier results and all three attempts are recorded in `research.md`. The benchmark test is opt-in via the environment variable and has no pytest `performance` marker.

## Review checklist

- Confirm all state outputs retain their documented Polars schemas and canonical ordering.
- Compare optimized and general results for formulas, stockpiles, treaty-limited flows, and treasury values.
- Exercise zero/empty inputs, absent optional fields, non-finite values, and repeated ticks.
- Do not mark SC-003 complete until the controlled benchmark demonstrates the threshold.
