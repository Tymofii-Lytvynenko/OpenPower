# Performance Gate Log

Optimization limit: maximum three measured implementation iterations per algorithm. A baseline does not consume an iteration.

| Operation / gate | Baseline | Iteration 1 | Iteration 2 | Iteration 3 | Status |
| --- | --- | --- | --- | --- | --- |
| Save representative full campaign, <300 ms | Median 33.413 ms; p95 47.249 ms. | — | — | — | Passed; no optimization required. |
| Load representative full campaign, <500 ms | Median 23.709 ms; p95 37.215 ms. | — | — | — | Passed; no optimization required. |
| Full simulation + save/load lifecycle | Prior full-world run exceeded 5 minutes and was interrupted while another unidentified high-memory Python process was resident; result is inconclusive and is not a save/load baseline. | — | — | — | Throughput warning only; no optimization attempted. |

## Baseline context

- Command: `$env:RUN_SAVE_IO_PERFORMANCE_CHECKS='1'; .venv\Scripts\python.exe -m pytest -s -q tests/test_save_io_performance.py`.
- Workload: production `DataLoader.load_initial_state()` output; 8 tables, 61,958 combined rows. Initial-state compilation is outside the timed region. Each of 9 samples replaces the same temporary save slot and then loads it; this is a warm, local-filesystem measurement, not a cold-start result.
- Runtime: Python 3.14.1, Polars 1.36.1, orjson 3.11.5; PyArrow is not installed (Polars' configured Parquet implementation completed the test successfully).
- Hardware/OS: Windows 11 build 26200, AMD Ryzen 5 2600 Six-Core Processor, approximately 68.65 GiB RAM. GPU is not material to this serialization-only gate.
- Storage: temporary save root on `C:` (NTFS, volume label `WINDOWS M.2`); 136.8 GB free when inspected. Physical disk model was not available from the system query, so the volume label is not treated as verified device type.
- Save median/p95: 33.413/47.249 ms. Load median/p95: 23.709/37.215 ms. The nearest-rank p95 of nine samples is the maximum sample.
- Optimization: 0 measured iterations for save and 0 for load; both median targets passed on baseline. No tuning was attempted.

Keep serialization-only timing separate from simulation ticks and application startup. If a future representative workload misses either gate, record each optimization attempt and stop after three measured iterations for that algorithm.
