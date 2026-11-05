# Research: UI Journey Test Harness

## Existing behavior

- `openpower ui-test list` emits the registered surface catalog as JSON.
- `openpower ui-test run <surface>` accepts journey and fixture files, a baseline image,
  visual tolerance, viewport dimensions, and output directory.
- Fixture and journey input must decode to JSON objects. Viewport dimensions must be
  positive, and visual tolerance must be between zero and one.
- `--matrix` uses four fixed viewport sizes: 800×600, 1024×768, 1280×720, and 1920×1080.
- `openpower ui-test all` runs registered surfaces in child processes and writes a
  `suite.json` summary. Each child has a 90-second timeout.
- `--rerun-failed` uses the prior `suite.json`, reruns only selected failures, and retains
  results that were not replaced.
- `openpower ui-test live-smoke` exercises the real Arcade runtime. It is separate from
  fixture-driven surface rendering.
- `docs/UI_TESTING.md`, `tests/test_ui_testability.py`, and JSON resources in `tests/ui/`
  describe and exercise the current workflow.

## Decisions recorded

| Decision | Rationale |
| --- | --- |
| Use a registered surface catalog | Stable IDs and explicit fixture contracts make runs reproducible. |
| Separate headless journeys from live smoke | A screenshot fixture cannot prove that real runtime input reaches the UI. |
| Isolate batch runs in child processes | A failed or timed-out surface does not prevent the suite summary from recording other pairs. |
| Preserve non-rerun suite results | Retrying a subset should not erase evidence for untouched pairs. |

## Validation boundary

This research records current source contracts and existing test/data locations. No UI
command or live client was launched during this documentation update.
