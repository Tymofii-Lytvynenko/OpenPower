# Implementation Plan: Headless Simulation Runner and Determinism Comparison

**Branch**: `119-headless-simulation-runner` | **Date**: 2026-10-21 | **Spec**: [spec.md](spec.md)

**Input**: Existing headless runtime and CLI behavior in `src/simulation/`, `src/cli.py`,
`src/server/session.py`, and the simulation tooling documentation.

## Summary

Document the existing deterministic headless run and comparison workflow. The runner
reuses `GameSession`, validates optional action scripts against registered action types,
advances a fixed simulation duration, collects diagnostics, fingerprints complete
persistent state, and writes JSON/JSONL artifacts. This specification records the
observable contract and does not introduce a new simulation path.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: Project runtime, Polars, orjson, standard-library argparse

**Storage**: JSON and JSONL run artifacts; optional exported state tables

**Testing**: Existing focused suites include `tests/test_headless_simulation.py` and
`tests/test_simulation_tooling.py`; this documentation task does not execute them.

**Target Platform**: Local development environments supported by OpenPower

**Project Type**: Python desktop game engine and CLI tooling

**Performance Goals**: A run's wall-clock speed is workload-dependent; gameplay time is
advanced by explicit fixed steps and is not derived from measured execution duration.

**Constraints**: Headless execution must not initialize the graphical client. Run IDs and
output paths must remain attributable to the resulting artifacts.

**Scale/Scope**: One session per run; repeated deterministic runs are configured by the
comparison command.

## Constitution Check

- **Layer separation**: The CLI delegates to `src/simulation`; simulation orchestration
  delegates to the server session and does not make the client authoritative.
- **Determinism**: Random seed, action order, fixed-step progression, and complete-state
  fingerprinting are explicit inputs or outputs.
- **Data integrity**: Diagnostics surface failed commands, system errors, invalid schema
  state, and broken references rather than substituting dummy state.
- **Status**: Aligned by the current code path and documented architecture.

## Project Structure

```text
src/
├── cli.py
├── simulation/
│   ├── actions.py
│   ├── artifacts.py
│   ├── comparison.py
│   ├── diagnostics.py
│   ├── fingerprint.py
│   ├── runner.py
│   ├── serialization.py
│   └── snapshots.py
└── server/session.py

tests/
├── test_headless_simulation.py
└── test_simulation_tooling.py
```

**Structure Decision**: The existing `src/simulation` package owns reusable run,
comparison, diagnostics, fingerprint, serialization, and snapshot behavior. `src/cli.py`
only parses command arguments and translates them to the simulation package.

## Complexity Tracking

No constitution exception or additional architectural layer is required.
