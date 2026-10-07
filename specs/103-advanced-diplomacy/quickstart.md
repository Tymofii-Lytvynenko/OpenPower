# Quickstart: Advanced Diplomacy

Run the peace-package, coalition, and war-exhaustion system tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_advanced_diplomacy_system.py tests/test_diplomatic_balance_system.py
```

Run related treaty, map-overlay, and persistence/IPC tests after changing schemas, events, or projections:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_treaty_specification.py tests/test_treaty_rules.py tests/test_treaty_trade_policy.py tests/test_map_visual_encoding.py tests/test_snapshot_protocol.py
```

Inspect the test state tables and event lists to verify same-tick updates. Acceptance also requires both war-side occupation orientations, no partial package mutation on invalid input, and current country/unit projections that the client can consume.
