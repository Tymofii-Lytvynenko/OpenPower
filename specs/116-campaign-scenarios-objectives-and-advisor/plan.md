# Implementation Plan: Campaign Scenarios, Objectives, and Advisor

**Branch**: `116-campaign-scenarios-objectives-and-advisor` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification in `specs/116-campaign-scenarios-objectives-and-advisor/spec.md`

## Summary

Close and validate the campaign layer around existing authoritative systems. `CampaignSetupSystem` applies a selected scenario once during bootstrap; `CampaignSystem` evaluates objectives after domain systems, then campaign outcomes, advisor recommendations, and scenario rules. Scenario measurements reuse territory, treaty, production, research, strategic, population, and political data. `CampaignPresenter` and the existing new-game/objectives views expose setup, progress, delegation, outcomes, and advisor priorities without allowing UI code to mutate state.

## Technical Context

**Language/Version**: Python 3.14.1
**Primary Dependencies**: Polars, pytest, existing game actions, system registration, AI delegation, persistence, and client ImGui components
**Storage**: Registered `GameState` Polars tables; scenario definitions and bounded setup/rule JSON; existing snapshots, IPC, and save files
**Testing**: pytest focused unit/integration/persistence tests plus an opt-in controlled performance gate
**Target Platform**: Authoritative headless simulation and Windows desktop client
**Project Type**: Data-oriented grand-strategy simulation with a passive client
**Performance Goals**: Evaluate 10,000 objectives and 5,000 advisor signals in under 500 ms when only affected conditions changed
**Constraints**: Reuse authoritative system outputs; apply setup only once; preserve sandbox play; deterministic boundary ordering; no implicit or out-of-scope authority; functional work takes precedence over further tuning
**Scale/Scope**: Scenario selection and setup, objective measurement/progress, outcomes, bounded delegation, advisor recommendations, campaign overview, and persistence/replay

## Constitution Check

- Gameplay policy stays in `modules/base/systems/world`; client views dispatch semantic actions and read presenter projections. **PASS**.
- Campaign and objective state remains in registered Polars tables with existing snapshot/save contracts. **PASS**.
- Objective metrics reuse existing authoritative system outputs; no duplicate economy, territory, treaty, resource, or military calculations are introduced. **PASS**.
- Existing system phases provide bootstrap setup and post-domain evaluation; no engine-loop special case is needed. **PASS**.
- Determinism is preserved through stable inputs and explicit evaluation order. **PASS**.
- The campaign performance gate already passed after three measured optimization iterations; do not spend a fourth iteration. Re-measure only to detect regressions; record and defer any failure. **PASS**.
- Excluded scope: multiplayer implementation and game-editor-only functionality remain out of scope under `specs/implementation-scope.md`. **PASS**.

## Project Structure

```text
modules/base/systems/world/
├── campaign_system.py             # Bootstrap setup, objective/outcome/advisor lifecycle
├── campaign_objective_policy.py   # Measurements over authoritative source tables
├── ai_system.py                   # Scope-bounded delegation context
└── registration.py                # Campaign setup and evaluation order
modules/base/
└── schema.py                      # Scenario, campaign, objective, delegation, and advisor tables
src/shared/
└── actions.py                     # Start-campaign and delegation commands
src/client/
├── tasks/new_game_task.py         # Authorized start action from selected scenario
├── views/new_game_view.py         # Scenario and actor selection
└── ui/panels/service/
    ├── campaign_presenter.py      # Country-scoped immutable overview projection
    └── objectives_panel.py        # Progress, deadline, delegation, and advisor display
tests/
├── test_campaign_system.py
├── test_campaign_presenter.py
├── test_campaign_performance.py
├── test_campaign_persistence.py
└── related scenario, AI, IPC, and save tests
```

**Structure Decision**: Continue using the existing bootstrap/post-process systems and their registered tables. Keep measurement code in a small policy module, presentation in the campaign presenter/panel, and authority in existing action/AISystem contracts. No parallel campaign runner or new dependency is needed.

## Implementation Sequence

1. Compare every FR/SC and edge case with the existing campaign system, presenter, schema, save/IPC behavior, and focused tests. Record only demonstrated gaps as implementation tasks.
2. Add or refine deterministic tests first for scenario setup/rejection, all supported measurement types, hold/deadline behavior, outcome precedence, scoped delegation/AI authority, stale advisor handling, persistence/replay, and overview projections.
3. Fix gaps in their owning layer without duplicating authoritative calculations or broadening delegation authority.
4. Run the focused functional/persistence quickstart. Run the controlled performance gate only as a regression check: its three optimization iterations are already recorded in `research.md`, and no fourth iteration is allowed.
5. Keep any rendered-client 30-second usability check separate from headless tests. Do not claim a manual UI pass without an accessible desktop client.

## Performance History Constraint

`research.md` records three measured iterations ending at 458.45 ms against the 500 ms gate. This algorithm has exhausted its optimization budget while passing. A later regression is a documented performance issue for future work; continue with other functional requirements rather than tuning it further in this pass.

## Complexity Tracking

No constitution violations or additional dependencies are planned.
