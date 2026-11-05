# Quickstart: Headless Simulation Runner

Run a seeded 30-day scenario with the base module:

```powershell
openpower sim run --mods base --days 30 --seed 42 --player UKR
```

Run a deterministic comparison and choose an output directory:

```powershell
openpower sim compare --mods base --days 30 --seed 42 --player UKR --runs 2 --output artifacts/sim-compare
```

Run an action-script scenario and save its artifacts to a named directory:

```powershell
openpower sim run --mods energy_crisis --days 30 --seed 42 --player UKR --actions modules/energy_crisis/scenarios/policy_response.json --output artifacts/energy-crisis
```

The run prints its run ID, final fingerprint, and final report path. A failing run or a
determinism mismatch returns a nonzero status. Inspect `final_report.json` and
`timeline.jsonl` in the selected output directory for diagnostics and event history.

This guide records the current CLI contract. Commands were not executed as part of the
documentation-only specification update.
