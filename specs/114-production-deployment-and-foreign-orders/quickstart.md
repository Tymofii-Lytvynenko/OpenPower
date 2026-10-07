# Quickstart: Production, Deployment, and Foreign Orders

Run the focused functional checks:

```powershell
$env:POLARS_MAX_THREADS = '1'
.venv\Scripts\python.exe -m pytest -q tests/test_production_capacity_policy.py tests/test_research_program_system.py tests/test_foreign_order_system.py tests/test_military_movement_spec.py tests/test_military_market_presenter.py tests/test_ai_policies.py tests/test_ai_integration.py
```

Run the opt-in combined scale gate:

```powershell
$env:POLARS_MAX_THREADS = '1'
$env:RUN_PRODUCTION_DEPLOYMENT_BENCHMARKS = '1'
.venv\Scripts\python.exe -m pytest -s -q tests/test_production_deployment_performance.py
```

Acceptance should cover priority allocation, pause/resume and preserved progress, single completion, valid domain deployment, route/access revocation, no active presence during transit, seller acceptance and pricing, cancellation costs, embargo rejection, used listing withdraw/purchase, duplicate transaction rejection, AI action parity, and persistence/replay of partial and in-transit state. Record each empirical result in `research.md`. A live-client test must verify that the player can determine ETA and destination within 30 seconds.
