# Data Model: Headless Simulation Runner

## Run configuration

`SimulationRunConfig` is immutable after construction and contains the project root,
active module IDs, optional save and player tag, run ID, duration, step/speed settings,
action script path, random seed, artifact directory, snapshot and diagnostics intervals,
table sample limit, table export flags, development mode, and fatal-error policy.

The CLI converts comma-separated module names into an ordered, de-duplicated tuple and
resolves relative input/output paths against the selected project root.

## Run report

`SimulationRunReport` records:

- run ID and output directory;
- final report and timeline paths;
- snapshot and table export paths;
- failure flag and failure reasons;
- diagnostic issue counts;
- final persistent-state fingerprint; and
- the final state summary.

## Diagnostics

Each `DiagnosticIssue` has a severity, stable code, message, optional table and column,
and a details mapping. Error diagnostics can be configured to fail the run; rejected
commands are warnings unless the runtime records them as failed commands.

## Action script

An action script contains ordered actions at scheduled simulation offsets. Each action
must resolve to a type handled by the loaded engine. The script cannot bypass the normal
command path or mutate state directly.

## Artifact layout

```text
<output-dir>/
├── run_config.json
├── timeline.jsonl
├── final_report.json
├── snapshots/<checkpoint>.json
└── tables/<checkpoint>/<table>.jsonl
```

The table directory is optional and is written only when enabled. The default run root is
`user_data/simulations/<run-id>`.
