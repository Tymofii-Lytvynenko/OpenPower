# Implementation Plan: Strategic Warfare and Missile Defense

**Branch**: `110-strategic-warfare-and-missile-defense` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Strategic weapon and missile-defense requirements in this directory. Multiplayer and game-editor-only functionality are out of scope under [implementation-scope.md](../implementation-scope.md).

## Summary

Complete the existing authoritative strategic-warfare system around the repository's typed `GameState` tables. Keep production orders, launch validation, research gates, deterministic defense, bounded impact, escalation, and AI policy in the base module; keep shared actions and scenario defaults as passive data; expose outcomes through the existing client presenter and panel. Close contract gaps for country approval, class-configured production/flight timing, UI coverage/defense estimates, and save/load/replay verification without replacing existing economy, diplomacy, military, or persistence systems.

## Technical Context

**Language/Version**: Python 3.14 runtime in the configured workspace.
**Primary Dependencies**: Polars, imgui-bundle, pytest; existing OpenPower engine and base module.
**Storage**: Typed Polars tables in `GameState`; existing snapshot, Arrow IPC, and save-game serializers.
**Testing**: Focused pytest suites for strategic resolution, AI policy, client projection/panel, schema/persistence, plus repository-wide pytest where runtime permits.
**Target Platform**: Headless authoritative simulation and the existing desktop client.
**Project Type**: Modular desktop strategy game with an authoritative simulation process.
**Performance Goals**: SC-007 resolves 1,000 pending strikes and 2,000 defense-layer evaluations in under 500 ms when regions are unchanged. The benchmark is already within budget after three measured optimization iterations; do not spend another optimization iteration on this gate.
**Constraints**: Preserve deterministic replay and existing action/table contracts; do not mutate `GameState` from the client; retain bounded aggregate effects; do not implement multiplayer or editor-only requirements.
**Scale/Scope**: Two strategic weapon classes when scenario data enables them, two ordered defense layers by default, ten configurable payload levels, and data-oriented batch processing for pending orders.

## Constitution Check

- **Layer boundaries**: Pass. Authoritative behavior remains in `modules/base`; shared files contain action/profile data only; client files derive read-only projections and dispatch actions.
- **Schema and data contracts**: Pass. Persist all lifecycle state in schema-registered tables so existing snapshots, IPC, and save/load carry it.
- **Modularity and SOLID**: Pass. Extend `StrategicWarfareSystem`, presenter, and panel at their current seams; do not add engine-loop or unrelated subsystem policy.
- **Commenting**: Pass. Prefer self-documenting names; comments added only to explain the reason for a non-obvious contract or bug fix, in English.
- **Empirical verification**: Pass with open manual client gate. Focused tests and deterministic persistence checks are automatable; rendered usability acceptance remains open if no live client is available.

## Design Decisions

1. Keep strategic inventory, orders, defenses, and impacts as typed `GameState` tables. The existing persistence pipeline serializes registered state tables and avoids feature-specific save-file code.
2. Keep `ActionLaunchStrategicStrike` as player/AI intent and validate it only in the authoritative system. Invalid actions must leave weapon inventory, reserves, and target state unchanged.
3. Add optional per-weapon research, flight, production, and readiness values. A positive `flight_minutes` configures class/scenario-specific strike resolution time; absent/non-positive values use the established global fallback. Production profiles require positive cost/duration, and new inventory passes through the configured readiness delay. This preserves current scenarios while enabling distinct ICBM/SLBM profiles.
4. Apply civilian approval effects to the authoritative `gvt_approval` field. Retain `approval_rating` support only for legacy/custom tables that expose that field and not `gvt_approval`.
5. Keep client defense forecasts explicitly informational. They display configured coverage and probability inputs without predicting the deterministic seeded result or changing simulation state.
6. Resolve interception in the configured layer order using deterministic rolls; serialize the attempt sequence with the order so audit and replay do not need transient caches.
7. Reuse the current three-iteration SC-007 performance evidence; functional fixes are not a reason to repeat or extend optimization work. Record any future measured regression as a performance issue rather than exceeding the iteration cap.
8. Add a durable, research-gated production queue only for scenario-configured designs with positive cost and duration. Existing scenarios with no production profile retain their current behavior; costs and durations remain data-defined rather than guessed in the simulation system.

## Project Structure

The feature stays within the existing code layout:

- `modules/base/schema.py`, `registration.py`, `systems/military/strategic_warfare_system.py`
- `modules/base/systems/world/bootstrap_system.py` and `systems/world/ai/strategic_warfare_policy.py`
- `src/shared/actions.py` and `src/shared/strategic_profiles.py`
- `src/client/ui/panels/military/presenter.py` and `strategic_warfare_panel.py`
- Root `tests/test_strategic_warfare_*.py` suites
- Design artifacts in this feature directory

**Structure Decision**: Extend the existing base-module system and client military panel rather than creating a parallel domain or persistence subsystem. Tests remain in the repository's root `tests/` suite.

## Complexity Tracking

No constitution violations or new architectural projects are proposed.
