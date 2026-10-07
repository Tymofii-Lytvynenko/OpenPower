# Quickstart: Polars AI Orchestration

Run AI framework, formula/action, and system integration tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_ai_framework.py tests/test_budget_ai_policy.py tests/test_ai_system.py
```

Run the opt-in 220-country formula scorer benchmark:

```powershell
$env:POLARS_MAX_THREADS = "1"
$env:RUN_AI_BENCHMARKS = "1"
.\.venv\Scripts\python.exe -m pytest -q -s tests/test_ai_performance.py
```

Latest controlled result (Python 3.14.1, Windows 11, Polars 1.36.1, one thread): scorer-only median **1.53 ms**, below the 2 ms requirement. The complete framework path (candidate generation, ranking, conflict resolution, and 220 action objects) measured **8.40 ms**, exceeding its 2 ms diagnostic target by 6.40 ms; the benchmark records this gap rather than hiding it. The one-thread setting is scoped to the repeatable 220-country benchmark, not imposed on the production worker. Polars reads `POLARS_MAX_THREADS` during process startup; see the [official thread-pool documentation](https://docs.pola.rs/api/python/stable/reference/api/polars.thread_pool_size.html). Do not generalize the benchmark result to a differently configured worker.

Latest full-suite regression: **684 passed, 16 skipped, 116 warnings, 190 subtests passed in 162.89 seconds**. The benchmark tests are opt-in and are run separately with the command above.
