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

## Bilateral offers

Run the simulation contracts for cash, region, and technology offers, including stale-asset rejection, atomic settlement, counters, expiry, withdrawal, and AI response:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_identity_bilateral_workflows.py
```

Run the synthetic Trade-panel journey at a standard and compact viewport:

```powershell
.\.venv\Scripts\python.exe main.py ui-test run trade --fixture tests/ui/fixtures/identity-trade.json --journey tests/ui/journeys/bilateral-trade.json --width 1280 --height 720
.\.venv\Scripts\python.exe main.py ui-test run trade --fixture tests/ui/fixtures/identity-trade.json --journey tests/ui/journeys/bilateral-trade.json --width 800 --height 600
```

The recording client verifies controls and dispatched actions; it does not settle the deal. The reported two-viewport run is documented in `docs/COUNTRY_IDENTITY_AND_BILATERAL_TRADE.md`; rerun the commands to reproduce it.
