# Political Lifecycle Validation Quickstart

Latest repository-wide run on 2026-10-07: **684 passed, 16 skipped, 116 warnings, and 190 subtests passed in 162.89 seconds**. This fresh rerun supersedes the older full-suite count noted in the historical validation paragraph below.

Run from the repository root using the project virtual environment.

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_political_initialization.py tests/test_political_schema.py tests/test_political_contracts.py tests/test_political_presenter.py tests/test_political_map_mode.py tests/test_political_law_transitions.py tests/test_political_elections.py tests/test_political_election_overrides.py tests/test_political_crises.py tests/test_political_regime_changes.py tests/test_political_ai.py tests/test_political_persistence.py tests/test_political_effect_integration.py tests/test_political_performance.py tests/test_game_state_ipc.py tests/test_schema_mod_migrations.py tests/test_layer_boundaries.py
```

The combined political, AI, persistence, schema, IPC, and layer-boundary matrix reports **71 passed in 9.73 s** on 2026-10-07 (Windows 11, Python 3.14.1, project virtual environment; 116 upstream pyglet `ctypes` deprecation warnings). This includes successful and failed regime changes, action authority, crisis type/deadline and support thresholds, bounded indicator and relation effects, cancellation/rescheduling, journal/history/events, and unchanged region ownership. Election coverage includes interval defaults/overrides, support and turnout snapshots, deterministic tie-breaking, coalition and succession fallbacks, due-time resolution, next-date scheduling, configured override permissions/date bounds/costs/cooldowns/consequences/rejection immutability, and read-only client projection/action dispatch. Political-crisis coverage includes multi-threshold escalation order, duplicate prevention, bounded attributed effects, recovery, notifications, and overview projection. Law-transition scenarios cover authority, allowed values, configured cost, cooldown, crisis guard, scheduled boundaries, carry-over/cancellation, bounded effects, journal/history/messages, and idempotent resolution. Cross-domain checks cover tax, labor/economic output, migration, rights/stability, readiness, effective dates, and unrelated-country invariance.

Pending political transitions/elections/crises pass the focused snapshot and save/load continuation tests. The historical full repository suite reported **524 passed, 4 opt-in performance skips, 173 subtests passed in 151.51 s**, including the real-session save/load round-trip; those four skipped gates were run separately and passed. The latest repository-wide run reports **683 passed, 16 skipped, 116 warnings, 190 subtests passed in 164.78 s** (2026-10-07). The opt-in gates are unrelated to political lifecycle; the focused political performance benchmark also passes below.

```powershell
.\.venv\Scripts\python.exe -m pytest -q -s tests/test_political_performance.py
```

The 10,000-country steady-state benchmark warms the lifecycle first, then measures three unchanged updates. Median runtime was **0.001 s**; all political table revisions remained unchanged. This meets the SC-007 threshold of 0.5 s on the current Windows/project-venv runtime; it does not measure cold initialization. Automated implementation and save/load gates are complete; manual interactive UI verification remains open.

## Language and religion identity policy extension

Run the identity-policy and layered-profile simulation contracts:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_identity_bilateral_workflows.py tests/test_data_loader_mod_layering.py
```

Run the Internal Laws identity journey at standard and compact sizes:

```powershell
.\.venv\Scripts\python.exe main.py ui-test run internal-laws --fixture tests/ui/fixtures/identity-trade.json --journey tests/ui/journeys/identity-policy.json --width 1280 --height 720
.\.venv\Scripts\python.exe main.py ui-test run internal-laws --fixture tests/ui/fixtures/identity-trade.json --journey tests/ui/journeys/identity-policy.json --width 800 --height 600
```

The implementation report records 20 tests across the identity workflow and data-layering modules, plus a 14-step identity journey at both viewport sizes. This was reported evidence in `docs/COUNTRY_IDENTITY_AND_BILATERAL_TRADE.md`; the tests were not rerun during this specification reconciliation. The synthetic UI journey verifies projection and action dispatch; the simulation tests remain responsible for daily share updates and political effects.
