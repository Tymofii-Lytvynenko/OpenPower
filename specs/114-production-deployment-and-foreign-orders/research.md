# Research: Production, Deployment, and Foreign Orders

## Decisions

- Keep production allocation, foreign contracts, used-unit listings, and deployment decisions in the existing authoritative military systems. Continue using the shared unit inventory, action journal, movement routes, treaty eligibility, and save contracts.
- Keep the public capacity allocator input/output as list-of-dictionaries for compatibility. Optimize internals only behind that boundary.
- Use the vectorized final-leg movement path only for the verified homogeneous, authorized route profile; retain the reference movement path for complex routes and access conditions.
- Stop performance work once the combined scale gate passes. The observed movement bottleneck was addressed in one iteration and production allocation in a second; no third iteration is needed.

## Environment and workload

- Date: 2026-10-07
- OS: Windows 11 build 26200; 12 logical CPUs; AMD Ryzen 5 2600
- Runtime: Python 3.14.1; Polars 1.36.1; `POLARS_MAX_THREADS=1`
- Combined workload: 50,000 queued domestic production orders and 100,000 route-bound transit records, with 1,000 due records. The test resets the authoritative tables between samples, performs three warm-up samples and records five measured samples. The gate is combined median below 1,000 ms.
- Benchmark command: `$env:POLARS_MAX_THREADS='1'; $env:RUN_PRODUCTION_DEPLOYMENT_BENCHMARKS='1'; .venv\Scripts\python.exe -m pytest -s -q tests/test_production_deployment_performance.py`

## Performance attempts and outcomes

| Stage | Change | Five combined samples (ms) | Median (ms) | Stage medians (production / movement, ms) | Outcome |
|---|---|---:|---:|---:|---|
| Baseline | Existing full-path production allocation and route movement | 5432.77, 5286.19, 5750.88, 5548.39, 5447.09 | 5447.09 | 794.73 / 4713.39 | Failed; 0/3 iterations |
| Iteration 1 | Add a guarded vectorized path for homogeneous authorized final-leg arrivals; complex routes remain on the reference path | 863.28, 993.30, 1163.48, 1201.61, 1071.06 | 1071.06 | 949.29 / 122.58 | Failed narrowly; 1/3 iterations |
| Iteration 2 | Remove redundant index/remaining/allocation maps from deterministic production capacity allocation while preserving its public row contract | 778.56, 782.28, 801.98, 796.16, 786.46 | 786.46 | 683.99 / 101.77 | Passed; stop optimization at 2/3 iterations |
| Acceptance rerun | No additional optimization; rerun after functional test additions | 833.41, 810.13, 890.13, 972.29, 936.46 | 890.13 | 773.52 / 116.60 | Passed; 1/1 benchmark test |

The passing iteration-2 median is 85.6% below baseline. The acceptance rerun remains 109.87 ms below the 1-second limit. Because the gate passes, no third measured optimization iteration was spent. No remaining observed scale-gate issue is deferred for this feature.

## Functional validation

- Focused quickstart functional command on 2026-10-07: `tests/test_production_capacity_policy.py tests/test_research_program_system.py tests/test_foreign_order_system.py tests/test_military_movement_spec.py tests/test_military_market_presenter.py tests/test_ai_policies.py tests/test_ai_integration.py` → **53 passed, 9 subtests passed** before adding the final presenter projection assertion.
- Final quickstart functional command with the presenter projection assertion: the same seven test modules → **54 passed, 9 subtests passed in 3.29s**.
- Foreign-order focused suite after adding cancellation, used-listing withdrawal/duplicate-purchase, and save/load continuation coverage: `tests/test_foreign_order_system.py` → **7 passed**.
- The persistence scenario compares production, deployment, route, contract, acceptance, inventory, and country tables across IPC snapshot and disk save/load, then advances both restored states through production and foreign-unit arrival; both continuations match and the contract reaches `delivered`.

## Remaining acceptance

- Automated tests exercise queue priority, pause/resume and partial work, single completion, route/domain delivery, treaty and authority rejection, seller standing acceptance, default 125% pricing, cancellation costs and relationship penalty, default 75% used pricing, listing withdrawal, embargo filtering, repeat-purchase idempotency, AI action parity, snapshot/save-load continuation, and the performance workload.
- Player-facing presenter tests verify queue ETA/capacity/funding/block reason and eligible foreign designs, seller acceptance, contract status, price, and reason. These do not substitute for interactive rendering verification.
- Manual desktop UAT for identifying production completion time and deployment destination within 30 seconds remains open: no targetable game client window was available during this run. Do not count headless or presenter tests as a UI pass.
