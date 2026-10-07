# Implementation Plan: Covert Operations and Counterintelligence

**Branch**: `109-covert-operations-and-counterintelligence` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/109-covert-operations-and-counterintelligence/spec.md`

## Summary

Implement covert cells and missions as authoritative, deterministic simulation state. Reuse the existing action, budget, movement-access, diplomacy, event, save/snapshot, and presentation contracts. Keep target-facing intelligence hidden until discovery; represent discoveries as confidence- and freshness-limited findings. The repository already contains the main system, policies, AI action path, and overview panel, so work should focus on verifying every functional requirement and correcting only demonstrated gaps.

## Technical Context

**Language/Version**: Python 3.14.1  
**Primary Dependencies**: Polars 1.36.1, existing OpenPower action/event and module-system interfaces  
**Storage**: Authoritative Polars tables in `GameState`; existing snapshot and save serialization  
**Testing**: pytest and standard-library unittest-compatible tests  
**Target Platform**: Windows desktop client with headless authoritative simulation; Python runtime  
**Project Type**: Desktop strategy game with a separate authoritative server/simulation process  
**Performance Goals**: 5,000 active cells plus 1,000 pending missions in <500 ms under the controlled single-thread benchmark  
**Constraints**: Preserve deterministic replay; no direct client mutation; do not leak undiscovered information; spend no more than three measured optimization iterations on a failing gate, recording attempts/results and then deferring any remaining performance issue.  
**Scale/Scope**: Cell recruitment/training/assignment/transit, eight mission profiles, resolution and consequences, counterintelligence coverage, AI, intelligence-sharing, persistence, and overview UI. Multiplayer is out of scope.

## Constitution Check

- Gameplay policy stays in `modules/base/systems/military`; common actions/events remain passive data contracts.
- Authoritative state uses Polars schemas; the client reads presentation projections and submits actions only.
- Covert outcomes use deterministic state-derived variation; invalid actions must not charge or mutate state.
- Feature coverage is validated with focused tests, a save/snapshot boundary check, and the isolated performance gate.
- No new architectural exception is required. Re-check after design: PASS.

## Project Structure

```text
modules/base/systems/military/
├── covert_operations_system.py   # Authoritative lifecycle, preparation, resolution
├── covert_policy.py              # Skill and bounded domestic coverage policy
├── movement_access.py            # Shared foreign transit eligibility
└── route_policy.py               # Shared route planning
modules/base/systems/world/ai/covert_policy.py
src/shared/actions.py
modules/base/schema.py
src/client/ui/panels/military/
├── covert_ops_panel.py
└── presenter.py
tests/
├── test_covert_operations_system.py
├── test_covert_ai_policy.py
├── test_military_presenter.py
├── test_game_state_ipc.py
└── test_covert_operations_performance.py
```

**Structure Decision**: Extend the existing military system and shared domain contracts. Do not create a second persistence, route, or intelligence-sharing subsystem.

## Implementation Sequence

1. Verify schema/actions, state lifecycle, resource charging, authority validation, and duplicate-action rejection.
2. Verify all mission profiles, deterministic results, bounded effects, detection/attribution, and secrecy projections.
3. Verify foreign transit, domestic counterintelligence coverage, AI parity, and allied intelligence confidence caps.
4. Verify save/load/snapshot/replay compatibility, including legacy empty tables.
5. Run the isolated 5,000-cell/1,000-mission gate. Tune only if it fails and for at most three measured iterations; record any still-open problem and move on.
6. Complete client acceptance manually when the desktop UI is available; headless checks do not substitute for that gate.

## Complexity Tracking

No constitution violations or additional dependencies are planned.
