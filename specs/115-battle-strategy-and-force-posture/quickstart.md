# Quickstart: Battle Strategy and Force Posture

Run focused functional and persistence coverage:

```powershell
$env:POLARS_MAX_THREADS = '1'
.venv\Scripts\python.exe -m pytest -q tests/test_battle_strategy_system.py tests/test_battle_strategy_persistence.py tests/test_battle_strategy_ai.py tests/test_battle_visibility.py tests/test_battle_allies.py tests/test_combat_system.py tests/test_occupation_resolution.py tests/test_battle_status_interface.py tests/test_schema_mod_migrations.py tests/test_client_snapshot_performance.py tests/test_game_state_ipc.py tests/test_save_writer_atomicity.py tests/test_ai_policies.py tests/test_ai_integration.py tests/test_layer_boundaries.py
```

Run the opt-in scale gate:

```powershell
$env:POLARS_MAX_THREADS = '1'
$env:RUN_BATTLE_STRATEGY_BENCHMARKS = '1'
.venv\Scripts\python.exe -m pytest -s -q tests/test_battle_strategy_performance.py
```

The scale gate uses 10,000 active posture records and 2,000 battles; its measured update median must be below 500 ms when only a bounded set of deadlines is due. If it fails, record the baseline and no more than three measured optimization iterations per failing algorithm.

Automated acceptance covers authority and force-type scoping, distinct projections, preset precedence, retreat/reorganization, occupation without sovereignty transfer, authorized battle detail, deterministic persistence, AI action parity, and performance. Live-client acceptance must still confirm that a player can identify each own force's posture, issuer, effective time, and next action within 30 seconds.
