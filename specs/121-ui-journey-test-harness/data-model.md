# Data Model: UI Journey Test Harness

## Surface catalog

Each registered surface has a stable string ID and enough metadata for the harness to
construct its renderer and input driver. The catalog is the set of supported test targets;
it is not a source-code scan.

## Journey and fixture inputs

- A **journey** is a JSON object with ordered interaction steps and optional fixture
  reference.
- A **fixture** is a JSON object that supplies deterministic table, global, and time
  overrides to the surface harness.
- Relative journey, fixture, baseline, and output paths resolve against the selected
  project root, unless the command uses an absolute path.

## Surface artifacts

A single surface run writes the report and actual screenshot under the selected output
directory. Optional baseline comparison adds its tolerance and comparison result to the
report.

## Suite report

`suite.json` contains a schema version, aggregate pass flag, and an array of run records.
Each record identifies the surface and viewport, pass status, process exit code, report
path, and captured output log. A rerun replaces matching failed pairs while retaining
unselected prior records.

## Live smoke artifacts

The live smoke output is stored independently from headless surface output so that
real-runtime input evidence cannot be confused with fixture-driven rendering evidence.
