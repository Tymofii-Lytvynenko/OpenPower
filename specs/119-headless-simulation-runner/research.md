# Research: Headless Simulation Runner

## Existing behavior

- `src/cli.py` exposes `openpower sim run` and `openpower sim compare` with shared inputs
  for project root, modules, years/days, seed, player, save, action script, output, run ID,
  snapshot interval, diagnostic interval, table export, and fatal diagnostic policy.
- `HeadlessSimulationRunner` builds a `GameConfig`, creates `GameSession.create_headless`,
  sets the selected speed, applies an optional `ActionScript`, and writes artifacts through
  `SimulationArtifactWriter`.
- The run uses explicit simulation steps and deterministic inputs. Runtime duration is
  measured for reporting, not fed back into gameplay time.
- `SimulationDiagnostics` inspects system events, command results, schema contracts,
  required tables, player/country identity, region and unit references, and finite country
  numeric values.
- `DeterminismComparisonRunner` executes repeated configurations and compares complete
  state fingerprints rather than only aggregate summaries.
- Existing artifact and behavior coverage is present in `tests/test_headless_simulation.py`
  and `tests/test_simulation_tooling.py`.

## Decisions recorded

| Decision | Rationale |
| --- | --- |
| Reuse the authoritative `GameSession` | Keeps module composition and state transitions consistent with interactive play. |
| Fingerprint complete persistent state | Summary metrics can match while individual tables or persistent fields diverge. |
| Keep diagnostics in run artifacts | Failures remain inspectable when the command returns a nonzero exit code. |
| Keep UI automation outside this feature | UI surface journeys have their own CLI contract in feature 121. |

## Open validation boundary

The code and existing focused tests define the current contract. This document does not
claim that those tests or sample commands were run during this documentation update.
