# Implementation Plan: Advanced Diplomacy & Coalition Systems

**Branch**: `103-advanced-diplomacy` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification at `specs/103-advanced-diplomacy/spec.md`

## Summary

Complete structured peace settlements and dynamic diplomatic balance using existing module-layer systems. `AdvancedDiplomacySystem` and `PeaceDealPolicy` own clause validation, multi-party responses, AI utility, ratification, and peace events; `DiplomaticBalanceSystem` owns expansion pressure, defensive coalitions, per-war exhaustion, and corresponding status events. Preserve existing treaty/war resolution, table schemas, and action/event APIs.

## Technical Context

**Language/Version**: Python (repository runtime in `pyproject.toml`)

**Primary Dependencies**: Polars DataFrames, existing `GameState`, shared `GameAction`/domain-event contracts.

**Storage**: Existing in-memory tables with the repository's save/IPC persistence path.

**Testing**: pytest unit and system integration tests.

**Target Platform**: OpenPower desktop and headless simulation runtime.

**Project Type**: Modular Python game engine.

**Performance Goals**: Evaluate and resolve a bounded peace package in the same simulation update; publish balance-state changes on the simulation update that processes the triggering event.

**Constraints**: Keep policy in `modules/base/systems/world`; use semantic actions and events; preserve player authorization, multi-party consent, existing treaty closure, deterministic ordering, and table contracts; no client or engine internals in gameplay systems.

**Scale/Scope**: Multiple active wars, participants, structured clauses (reparations, territory, treaty annulment, demilitarization), rolling one-year expansion events, coalition pacts, and per-country/per-war exhaustion state.

## Constitution Check

**Before research**

- Layer boundaries: PASS — behavior stays in module systems, shared actions/events remain passive data contracts, and UI reads replicated state.
- Data contracts: PASS WITH VERIFICATION — new state uses existing schema tables and `GameState` table APIs; migrations/persistence must retain defaults and types.
- Modularity/SOLID: PASS — validation/utility policy is separated from system orchestration, balance policy is a focused system, and no inheritance extension is required.
- Empirical verification: PASS WITH OPEN COVERAGE — existing integration tests cover core package/coalition/exhaustion paths; remaining directional, AI-obligation, and IPC/UI cases are explicit tasks.

**After design**: no cross-layer imports, table-schema redesign, or new dependencies are proposed. Regression and persistence/IPC checks remain required.

## Design and Research

See [research.md](research.md), [data-model.md](data-model.md), [contracts/diplomacy-events.md](contracts/diplomacy-events.md), and [quickstart.md](quickstart.md).

### Implementation locations

```text
modules/base/systems/world/
├── advanced_diplomacy_system.py   # Deal lifecycle, application, AI responses, events
├── peace_deal_policy.py           # Clause normalization, validation, and utility scoring
├── diplomatic_balance_system.py   # Expansion pressure, coalitions, and war exhaustion
├── territory_system.py            # Ownership and occupation fact events
└── treaty_diplomacy.py            # Existing treaty/war resolution and coalition commitments

modules/base/schema.py              # Economic/diplomatic state tables and defaults
src/shared/actions.py               # Peace-package and response commands
src/shared/events.py                # Peace, ownership, expansion, coalition, exhaustion events
src/client/controllers/viewport_controller.py
src/client/ui/panels/military/war_list_panel.py
tests/test_advanced_diplomacy_system.py
tests/test_diplomatic_balance_system.py
```

**Structure Decision**: Extend the existing diplomacy/balance systems and schema registry; no new service boundary or project structure is needed.

## Complexity Tracking

No constitution exception is approved. The optional AI archetype field defaults to a neutral `pragmatic` profile, preserving behavior for existing saves/content unless an archetype is configured.
