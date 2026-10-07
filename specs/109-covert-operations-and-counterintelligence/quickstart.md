# Quickstart: Covert Operations

Run the functional suite in a PowerShell session:

```powershell
$env:POLARS_MAX_THREADS = '1'
.venv\Scripts\python.exe -m pytest -q tests/test_covert_ai_policy.py tests/test_covert_operations_system.py tests/test_ai_policies.py tests/test_ai_integration.py tests/test_military_presenter.py tests/test_game_state_ipc.py
```

Run the isolated controlled performance gate:

```powershell
$env:POLARS_MAX_THREADS = '1'
$env:RUN_COVERT_BENCHMARKS = '1'
.venv\Scripts\python.exe -m pytest -s -q tests/test_covert_operations_performance.py
```

Acceptance coverage should include recruitment, training, all mission types, target validity, budget rejection, repeat-action rejection, deterministic replay, discovery/attribution visibility, AI action submission, transit revocation, domestic security diminishing returns, allied intelligence confidence caps, and snapshot/save compatibility. Record empirical results in `research.md`. A desktop acceptance pass must verify the overview visually and confirm target-side secrecy; a headless test is not a substitute.
