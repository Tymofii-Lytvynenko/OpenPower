# Quickstart: Campaign Scenarios, Objectives, and Advisor

Run focused campaign, presentation, AI delegation, persistence, and layer-boundary coverage:

```powershell
$env:POLARS_MAX_THREADS = '1'
.venv\Scripts\python.exe -m pytest -q tests/test_campaign_system.py tests/test_campaign_presenter.py tests/test_objectives_panel.py tests/test_campaign_selection.py tests/test_campaign_persistence.py tests/test_campaign_performance.py tests/test_ai_policies.py tests/test_ai_integration.py tests/test_game_state_ipc.py tests/test_save_writer_atomicity.py tests/test_layer_boundaries.py
```

Run the controlled scale gate only as a regression check. Three optimization iterations are already recorded in `research.md`; do not perform another tuning iteration.

```powershell
$env:POLARS_MAX_THREADS = '1'
$env:OPENPOWER_PERFORMANCE_TESTS = '1'
.venv\Scripts\python.exe -m pytest -s -q tests/test_campaign_performance.py
```

The automated scenarios verify one-time start setup, objective measurements/progress/evidence, deadlines and hold rules, deterministic outcomes, bounded delegation, AI policy parity, stale advisor recommendations, and persisted campaign state. A live-client check must separately confirm a player can identify the next objective action and its deadline within 30 seconds; do not infer this from headless tests.
