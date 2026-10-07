# Performance Gate Log

Optimization budget: at most three measured implementation iterations per algorithm. A baseline measurement is not an optimization iteration.

| Algorithm / gate | Baseline measurement | Iteration 1 | Iteration 2 | Iteration 3 | Status |
| --- | --- | --- | --- | --- | --- |
| Data Inspector, 10,000-row visible frame <4 ms | Windows 11 Pro, AMD Ryzen 5 2600, Python 3.14.1, Polars 1.36.1; synthetic 10,000-row/two-column frame. CPU-only full-match search + sort median **4.314 ms**, p95 **10.027 ms** (11 samples); cached projection median **0.0122 ms**, p95 **0.0149 ms** (11 samples). This omits ImGui row construction and GPU presentation; the existing headless test verifies that only visible rows are drawn. | — | — | — | Cold search/sort projection exceeds 4 ms and is a future performance issue; cached projection is below target. Full rendered-frame gate remains pending. No optimization iteration used. |
| Dashboard slider responsiveness, 60+ FPS | Not yet measured in a live desktop session. | — | — | — | Pending empirical UI timing; no optimization iteration used. |

## Functional verification

- Focused dashboard/politics/inspector suite: **65 passed** (includes budget action, ImPlot context, resource projection, politics drift, and previous political integration coverage).
- Broader political regression suite: **96 passed** across political, crisis, migration, economic-health, and random-event integration tests.
- Runtime warnings in these runs: 116 existing Pyglet `ctypes._pointer_type_cache` deprecation warnings; no test failures.

The initial seven-sample exploratory run used a narrower query and measured 4.023 ms for the cache-miss transform; the 11-sample full-match run above is the recorded baseline. No code changes were made between those measurements.

Record future measurements with machine/OS, display resolution, dataset shape, warmup/sample count, median and p95. After three failed tuning iterations, stop and retain the final outcome here as deferred work.
