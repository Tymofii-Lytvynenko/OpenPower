# Implementation Plan: UI Journey Test Harness

**Branch**: `121-ui-journey-test-harness` | **Date**: 2026-10-21 | **Spec**: [spec.md](spec.md)

**Input**: Existing CLI and surface inspection behavior in `src/cli.py` and
`src/client/ui/testing/`, with workflow guidance in `docs/UI_TESTING.md`.

## Summary

Document the existing UI validation harness. It lists known surfaces, builds deterministic
fixtures, applies JSON journeys, captures screenshots and reports, runs suites in isolated
processes, retries failed surface/viewport pairs, and offers a real Arcade live smoke
command.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: Arcade, Dear ImGui, orjson/JSON, project UI testing utilities

**Storage**: JSON journey/fixture files and JSON/PNG report artifacts

**Testing**: Existing focused coverage includes `tests/test_ui_testability.py` and
surface-specific UI journeys under `tests/ui/`; this documentation update does not
execute them.

**Target Platform**: Supported OpenPower desktop development environments

**Project Type**: Python desktop game client and developer tooling

**Performance Goals**: Each isolated UI subprocess has a 90-second timeout; no frame-time
target is set for the harness itself.

**Constraints**: Headless surface inspection and live Arcade smoke runs are separate
validation modes. Reports must retain enough context to reproduce a surface/viewport run.

**Scale/Scope**: One or more registered surfaces, at one viewport or the four-size matrix.

## Constitution Check

- **Passive client boundary**: The harness renders and dispatches semantic input through
  existing UI paths; it does not directly mutate authoritative game state.
- **Layer separation**: CLI dispatches into `src/client/ui/testing`; gameplay logic remains
  in module systems.
- **Failure visibility**: Invalid surface input, child-process failure, and timeout are
  represented in reports and command status.
- **Status**: Aligned with the client and UI testing boundaries.

## Project Structure

```text
src/
├── cli.py
└── client/ui/testing/
    ├── catalog.py
    ├── driver.py
    ├── fixtures.py
    ├── harness.py
    ├── journey.py
    ├── live_smoke.py
    ├── surface.py
    └── visual_diff.py

tests/ui/
├── fixtures/
├── journeys/
└── *.json
```

**Structure Decision**: Keep surface discovery, fixture application, journey execution,
render capture, and visual comparison in the reusable client testing package. Use the CLI
as the command boundary and child processes for batched surface runs.

## Complexity Tracking

No constitution exception or additional architectural layer is required.
