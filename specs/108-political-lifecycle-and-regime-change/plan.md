# Implementation Plan: Political Lifecycle and Regime Change

**Branch**: `108-political-lifecycle-and-regime-change` | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

## Summary

Activate the existing country government and law seed data as an authoritative, deterministic lifecycle. Keep political rules inside the base module, expose intent through shared actions, persist state in versioned Polars tables, and publish effects/events for existing budget, economy, migration, military, diplomacy, and client systems to consume.

## Technical Context

**Language/Version**: Python 3.12 (repository virtual environment)
**Primary Dependencies**: Polars; existing OpenPower `ISystem`, action journal, AI framework, and UI toolkit
**Storage**: `GameState.tables` Polars frames; existing snapshot IPC and save/load migration paths
**Testing**: pytest with unit, integration, persistence, UI-projection, and controlled performance tests
**Target Platform**: Windows desktop client and headless authoritative simulation
**Project Type**: Modular desktop simulation with headless server process
**Performance Goals**: Incremental unchanged political state for 10,000 countries under 500 ms; no full-world scans on unchanged updates
**Constraints**: Preserve existing ownership, stability drift, economy, migration, military, treaties, action ordering, and passive-client boundaries; deterministic replay; no random choices without persisted seeded state
**Scale/Scope**: All countries, government forms, laws, parties, elections, domestic political crises, save/load, and one overview projection

## Constitution Check

- PASS: gameplay policy belongs in `modules/base/systems/politics`; shared action/event dataclasses remain data-only.
- PASS: authoritative values remain Polars tables and are normalized through `modules/base/schema.py`.
- PASS: clients submit actions and render presenter projections; they never mutate `GameState`.
- PASS: political systems publish bounded effects/events; economy, migration, and military retain their existing calculations.
- PASS: deterministic tie-breaking, idempotent due processing, and empirical tests are required before marking tasks complete.
- PASS: additions compose policies and dedicated systems instead of widening unrelated system responsibilities.

## Design Decisions

1. Extend the seeded government/law records in place with canonical runtime tables; do not duplicate or replace the seed catalog.
2. Process human and AI intents through the same authoritative action handlers, authorization checks, and journal results.
3. Resolve due transitions in a stable order at simulation boundaries. Store deadlines and decision evidence in persistent rows.
4. Keep approval, stability, and corruption as separate bounded values. Publish named, attributable effect records instead of rewriting dependent formulas.
5. Use scenario data for government-form rules, party positions, election intervals, crisis thresholds, and carry-over behavior. A four-game-year default applies only when no rule is configured.
6. Treat campaign history/messages as durable evidence; do not infer political causes from a changed value alone.

## Project Structure

```text
modules/base/schema.py
modules/base/registration.py
modules/base/systems/politics/
  politics_system.py
  political_lifecycle_system.py
  political_policy.py
  election_policy.py
  law_transition_policy.py
  political_effect_policy.py
  political_crisis_policy.py
src/shared/actions.py
src/shared/events.py
src/shared/system_interfaces.py
src/server/state_migrations.py
src/client/ui/panels/politics/
  political_overview_presenter.py
  political_overview_panel.py
tests/
  test_political_*.py
specs/108-political-lifecycle-and-regime-change/
  contracts/
  data-model.md
  quickstart.md
```

**Structure Decision**: Follow the existing module-owned gameplay-system pattern. Pure policy helpers are composed into an authoritative system; shared contracts carry requests and outcomes; a presenter projects state for the UI.

## Phase 0: Research Findings

See [research.md](research.md). Repository inspection found that `politics_system.py` currently owns weekly stability drift and consumes migration/event approval signals; `countries` carries separate approval/stability/corruption columns; seeded laws/governments already exist; and module systems use shared actions, journal results, schema tables, notifications, snapshots, and save migrations. No external API or dependency is needed.

## Phase 1: Data Model and Contracts

See [data-model.md](data-model.md) and [contracts/political-lifecycle.md](contracts/political-lifecycle.md). The design adds normalized government, party, law-transition, election, crisis, and political-cause records while retaining the seed catalog and existing country columns as compatibility inputs.

## Validation Gates

- Unit-test bounded value updates, voter eligibility, deterministic support/turnout, law permissions/costs, transition carry-over, and crisis thresholds.
- Integration-test action authority, due-date ordering, published effects, AI decisions through the same handlers, and message/history evidence.
- Save/load and snapshot tests must preserve pending dates, votes, transitions, and next outcomes.
- Run the political-focused matrix after each phase; repository-wide validation remains required before feature completion.
- Exercise 10,000 unchanged country records under 500 ms with a controlled benchmark; record hardware/runtime and result.

## Performance Evidence

The controlled steady-state check in `tests/test_political_performance.py` warms a 10,000-country political state, then measures three unchanged updates. The median was **0.001 s** (2026-10-07, Windows project virtual environment), and table revisions remained stable. Cold initialization and the full-repository suite are separate, still-open validation items.
