# Strategic Warfare Validation Quickstart

Run from the repository root with the configured virtual environment.

## Focused automated checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_strategic_warfare_system.py `
  tests/test_strategic_warfare_ai_policy.py `
  tests/test_strategic_warfare_panel.py `
  tests/test_strategic_warfare_persistence.py `
  tests/test_research_program_system.py
```

Expected results: invalid launches or production orders do not consume weapons or funds; research-gated production completes only at its configured ETA; per-weapon timing and legacy global timing are deterministic; the defense order/probabilities and interception stop are recorded; civilian approval uses the authoritative country schema; AI and human launch paths share the same validation; snapshots, IPC, save/load, and replay continue pending production and strikes identically.

**Latest focused run**: 2026-10-07 — 42 passed in 3.09 seconds.

**Latest repository-wide run**: 2026-10-07 — `pytest -q`: 917 passed, 25 skipped, 116 warnings, 239 subtests passed in 832.53 seconds (exit code 0). This verifies automated integration only; it does not satisfy the rendered-client acceptance below.

## Performance gate

SC-007 is opt-in and was already measured through its full three-iteration budget. Historical timings and the passing regression rerun are recorded in [research.md](research.md). Do not rerun as an optimization attempt; if a future change requires a regression check, run:

```powershell
$env:OPENPOWER_PERFORMANCE_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest -q tests/test_strategic_warfare_performance.py
Remove-Item Env:OPENPOWER_PERFORMANCE_TESTS
```

The benchmark must resolve exactly 1,000 orders and 2,000 defense attempts in under 500 ms. Any failed future gate must be logged with its measured duration and iteration count before moving on.

## Scenario weapon profiles

`state.globals["strategic_weapon_profiles"]` may configure `icbm` and `slbm` designs. ICBM remains enabled by default for compatibility; SLBM rows are created only when an SLBM profile is supplied. Each profile can set `range_km`, `payload_level`, `max_payload_level`, `required_research_level`, `initial_quantity`, `initial_ready`, `readiness_minutes`, `flight_minutes`, `launch_cost`, `production_cost`, and `production_minutes`. Values are scenario data, not engine balance defaults. Existing `strategic_weapon_production_profiles` entries remain supported and are overridden field-by-field by `strategic_weapon_profiles`.

## Manual rendered-client acceptance

Open a scenario with an owned strategic weapon, at least one enemy target region, and researched/fielded defense. Confirm the panel exposes weapon readiness/range, selectable payload profiles, target validity, authorization guidance, pending order, defense coverage and configured interception estimate, and recent outcomes. Launch against both covered and uncovered regions and confirm the panel's pre-resolution estimate is informational while the eventual outcome follows deterministic defense resolution. Record the 30-second inspection result for SC-006 and the payload/coverage result for SC-010. Do not count headless panel tests as rendered-client acceptance.
