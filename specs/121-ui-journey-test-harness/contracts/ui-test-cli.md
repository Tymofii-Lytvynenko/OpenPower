# Contract: UI Test CLI

## Commands

```text
openpower ui-test list
openpower ui-test run <surface> [--journey PATH] [--fixture PATH] [--baseline PNG]
  [--tolerance FLOAT] [--width PX] [--height PX] [--matrix] [--output PATH]
openpower ui-test all [--rerun-failed] [--matrix] [--output PATH]
openpower ui-test live-smoke [--output PATH]
openpower ui-test budget [--output PATH] [--width PX] [--height PX]
```

All commands that resolve project files accept `--project-root`. Default viewports are
1920×1080 except the legacy budget command, whose default is 1280×1000. The matrix option
selects 800×600, 1024×768, 1280×720, and 1920×1080.

## Input validation

- Width and height must be greater than zero.
- Visual tolerance must be between 0 and 1 inclusive.
- Fixture and journey files must contain JSON objects.
- The selected surface must be present in the registered catalog.

## Result behavior

- A run writes a surface report and actual image under its output directory.
- A batch writes `suite.json`; the aggregate command status is successful only when every
  recorded run passes.
- Each child run is limited to 90 seconds. Timeout and nonzero child exit are recorded as
  failed runs.
- Live smoke executes through the real Arcade runtime and writes to its own output path.
