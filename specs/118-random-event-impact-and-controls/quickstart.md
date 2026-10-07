# Quickstart: Random Event Impact and Controls

## Focused validation

Run from the repository root with the project virtual environment active:

```powershell
python -m pytest tests/test_random_event_contracts.py tests/test_random_event_policy.py tests/test_random_events_system.py tests/test_random_event_responses.py tests/test_random_event_effects.py tests/test_random_event_domain_effects.py tests/test_random_event_controls_integration.py tests/test_random_event_ai_policy.py tests/test_random_event_acceptance.py tests/test_event_feed_presenter.py tests/test_random_event_persistence.py tests/test_random_event_performance.py tests/test_population_system.py tests/test_migration_system.py tests/test_economic_health_system.py tests/test_regional_infrastructure_system.py tests/test_infrastructure_integration.py tests/test_economic_health_integration.py tests/test_schema_mod_migrations.py tests/test_engagement_layer_boundary.py tests/test_news_panel_controls.py -q
```

This matrix covers catalog validation, due-boundary eligibility, deterministic triggers/severity, category/global disable, cooldown and active caps, atomic response rejection, accepted response cost/mitigation, AI responses, domain effects, legacy active-event migration, snapshot/save round-trip, readable recent-event details, malformed UI settings, stable effect bounds, schema migration, and layer boundaries.

## Existing downstream regression

```powershell
python -m pytest tests/test_regional_infrastructure_system.py tests/test_infrastructure_integration.py -q
```

Existing earthquake/flood/etc. trigger facts must continue to create one bounded infrastructure damage record per event/category, not duplicate damage on later ticks.

## Full repository check

```powershell
python -m pytest -q
```

Record skipped, failed, and environment-dependent tests separately. Do not report SC-007 as passed from a small unit test: run the dedicated benchmark with 10,000 instances and 100,000 effects, advancing only due rows, and report elapsed time and machine/runtime details.

## Recorded validation

- Latest official focused matrix: **129 passed** (2026-10-07; Windows, project virtual environment; 9.56 s; 116 upstream Pyglet `ctypes` deprecation warnings). The opt-in history benchmark is separate and was not part of this matrix.
- Expanded focused matrix: **150 passed** (2026-10-07; project virtual environment, Windows; 10.66 s; 116 upstream pyglet `ctypes` deprecation warnings). This includes the quickstart random-event matrix plus history, campaign, and AI-framework regressions.
- Due-record benchmark: **1 passed**; 10,000 active instances and 100,000 effect records completed in **0.66 s** pytest call time (0.96 s total; 2026-10-06).
- Latest repository suite: **683 passed, 16 skipped, 190 subtests passed** (2026-10-07; Windows, Python 3.14.1, project virtual environment; 164.78 s; 116 upstream Pyglet `ctypes._pointer_type_cache` deprecation warnings). The 16 default skips comprise opt-in performance workloads, two live GPU atlas checks, and the live globe shader check; consult each feature's performance gate for its separately measured result.
- The expanded random-event/history/campaign/AI focused matrix previously reported **150 passed** (2026-10-07; 10.66 s). The dedicated 10,000-instance/100,000-effect due-record benchmark reported **1 passed**, 0.66 s pytest call time (0.96 s total; 2026-10-06). The earlier save/load stress scenario reported **1 passed, 168 subtests passed in 41.45 s**.
- Interactive client check: pending; requires a human-visible game session.
- UI availability recheck on 2026-10-07: the connected computer-use surface reported no native apps and no tabs in Chrome, the in-app browser, or Codex MCP Apps. The human-visible event/control workflow was therefore not performed; T026 remains open rather than being inferred from headless coverage.

## Interactive check

Start a single-player game, enable one category, and observe an event through the event feed. Confirm its location, severity, effect summary, response availability, and recovery/expiry are visible. Submit a valid response and an invalid/underfunded one; verify only the valid action changes funds and instance state. Also disable that category and confirm no new event appears after the next roll boundary while already active events follow their declared completion behavior.

See [contracts/random-events.md](contracts/random-events.md) for command and persistence boundaries and [data-model.md](data-model.md) for record lifecycle.
