# Implementation Plan: Battle Strategy and Force Posture

**Branch**: `115-battle-strategy-and-force-posture` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/115-battle-strategy-and-force-posture/spec.md`

## Summary

Complete the authoritative command-intent layer around the existing two-side battle resolver. Keep per-force postures, command history, retreat/regroup routes, and military occupation in the existing military module, while the resolver retains battle identity, round progression, casualties, and outcome. Close demonstrated gaps in information authorization and scenario-specific/AI command behavior; otherwise add focused tests around the implementation already present.

## Technical Context

**Language/Version**: Python 3.14.1  
**Primary Dependencies**: Polars 1.36.1; existing actions/events, movement, access, war, combat, and authority policies  
**Storage**: `GameState` Polars tables and scenario globals; persisted with existing save/IPC contracts  
**Testing**: pytest and standard-library unittest-compatible tests  
**Target Platform**: Windows desktop client and headless authoritative simulation  
**Project Type**: Data-oriented grand-strategy simulation and desktop client  
**Performance Goals**: 10,000 active force postures and 2,000 battles under 500 ms when only due orders advance  
**Constraints**: Preserve the existing two-side resolver and readiness timing; do not grant ally command implicitly; keep client passive; allow at most three measured optimization iterations per failing algorithm and defer after the third if still failing.  
**Scale/Scope**: Per-force commands and presets, attack/defense projections, back-off, retreat and regroup, occupation control, battle summaries, AI parity, persistence, and authorized UI projections.

## Constitution Check

- Gameplay decisions remain in `modules/base/systems/military`; UI only sends actions. **PASS**.
- Authoritative state remains in Polars tables and global scenario configuration. **PASS**.
- Command strategy composes the existing movement, war, authority, readiness, and combat policies rather than replacing them. **PASS**.
- Deterministic decisions use ordered data and existing `GameState` time; no new dependency is planned. **PASS**.
- Empirical test and benchmark evidence are required before declaring automated criteria complete. **PASS**.

## Project Structure

```text
modules/base/systems/military/
├── battle_strategy_system.py   # Authoritative orders, modifiers, retreat, reorganization, occupation
├── combat_system.py            # Existing two-side battle resolver consumes unit projections
├── route_policy.py             # Existing retreat/return route planning
└── movement_access.py          # Existing transit/stationing authorization
src/shared/
├── actions.py                  # Battle strategy and occupation commands
└── events.py                   # Existing event contracts extended only if needed
src/client/ui/panels/military/
├── battle_overview_panel.py    # Per-type commands and battle summaries
└── presenter.py                # Authorized summary projections
modules/base/schema.py          # Posture, command, casualty and occupation schemas
tests/
├── test_battle_strategy_system.py
├── test_battle_strategy_performance.py
├── test_battle_visibility.py
├── test_occupation_resolution.py
└── related battle/combat/AI/persistence suites
```

**Structure Decision**: Extend the currently registered `BattleStrategySystem` and existing `CombatSystem`; do not create another battle lifecycle or combat side. Restrict shared-layer edits to serializable actions/events and keep presentation filtering in the client presenter.

## Implementation Sequence

1. Establish focused coverage for posture projections, authority, presets and specific overrides, retreat/reorganization, occupation, event/history output, and save/snapshot continuation.
2. Verify and correct authorized battle-summary projections before exposing participant/loss details in the overview.
3. Verify AI command proposals use the same authorized `ActionSetBattleStrategy` contract, or record the exact unsupported behavior.
4. Run the 10,000-posture/2,000-battle benchmark. If it misses, measure a baseline and allow at most three optimization iterations for the failing algorithm; stop as soon as it passes.
5. Run the quickstart functional suite and leave live-client UAT open if no targetable client is available.

## Complexity Tracking

No constitution violations or additional dependencies are planned.
