# Freeplay Core Loop Acceptance Quickstart

This quickstart describes the automated evidence to capture after implementation. It is not an instruction to perform manual desktop acceptance.

## Before Running Acceptance

1. Start from a clean, supported local environment with the project's Python dependencies installed.
2. List registered UI surfaces with `openpower ui-test list` and select the freeplay journey surface added by this feature.
3. Keep the generated JSON reports, screenshots, and process logs with the run output; do not treat a screenshot as a substitute for state assertions.

## Acceptance Sequence

1. Run focused launch/session tests for country selection with no scenario id:

   ```powershell
   uv run --frozen pytest -q tests/test_new_game_view_coverage.py tests/test_freeplay_start_task.py
   ```

2. Run the deterministic core-loop and freeplay save/load acceptance:

   ```powershell
   uv run --frozen pytest -q tests/test_freeplay_core_loop.py tests/test_freeplay_save_load.py
   ```

3. List registered UI surfaces, then run the freeplay journey at the standard viewport:

   ```powershell
   openpower ui-test list
   openpower ui-test run freeplay-core-loop --fixture tests/ui/fixtures/freeplay_core_loop.json --journey tests/ui/journeys/freeplay_core_loop.json --output artifacts/ui/freeplay-core-loop --width 1280 --height 720
   ```

4. Record exact automated commands, exit codes, and artifact paths in this feature's `research.md` when implementation is complete.

## Expected Outcome

Every acceptance command exits successfully; state assertions confirm authoritative consequences; the UI journey report contains the selected surface, viewport, interaction result, and screenshot path. Any failure must preserve its diagnostic output and remain an open task. No manual desktop step is part of the release criteria.
