# Implementation Plan: Migration and Border Mobility

**Branch**: `107-migration-and-border-mobility` | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification in `/specs/107-migration-and-border-mobility/spec.md`

## Summary

Add deterministic domestic and international migration to the existing demographic simulation without introducing a second population ledger. `regions.pop_14`, `regions.pop_15_64`, and `regions.pop_65` remain authoritative. A registered gameplay system evaluates connected regional routes, effective-dated national policy, diplomatic restrictions, and destination capacity; it records auditable flows and moves integer cohort counts only at the completion boundary. Shared action/event contracts, scheduled policy transitions, AI policy selection, political/economic signals, schema-backed persistence, and a passive player-facing summary complete the feature.

## Technical Context

**Language/Version**: Python 3.14; type-annotated Python modules.

**Primary Dependencies**: Polars/Arrow data frames, existing OpenPower system/action/event contracts, `imgui-bundle` for the current client UI.

**Storage**: Typed `GameState` tables normalized through `WorldSchemaRegistry`; the existing save/load, IPC snapshot, and replay mechanisms persist tables and journal events.

**Testing**: pytest, including unit, integration, schema/persistence, UI-presenter, layer-boundary, determinism, and opt-in controlled performance tests.

**Target Platform**: Existing Windows desktop client and headless/server simulation runtime.

**Project Type**: Python modular game simulation with desktop client.

**Performance Goals**: A controlled batch of 10,000 pending flows resolves in under 250 ms. Normal ticks process due flows and dirty route endpoints only; unrelated route pairs are not recomputed.

**Constraints**: No direct client state mutation; no engine/core policy logic; cohort values remain non-negative integers; routes and policy decisions are deterministic; old saves without migration tables normalize to empty/default state; preserve original population totals on load.

**Scale/Scope**: Regional cohorts and connected region pairs across the loaded world; one effective migration policy and one summary per country, persisted directional flow records, and derived country-level migration signals.

## Constitution Check

- **Layer separation**: PASS. Gameplay policy/system in `modules/base`; serializable data contracts in `src/shared`; presentation only in `src/client`; no engine or server simulation logic changes.
- **Data-oriented state**: PASS. Policies, flows, and signals use registered Polars table schemas; region cohorts remain the single authoritative population source.
- **Modular/SOLID design**: PASS. Separate deterministic calculation/eligibility policy from the orchestration system, AI decision policy, and UI presenter; register the system through the base module.
- **Commenting rules**: PASS. Keep code self-documenting; add English rationale comments only where a non-obvious constraint or bug fix needs explanation.
- **Empirical verification**: PASS WITH GATES. Run targeted and compatibility suites, serialization/replay tests, repeat-run determinism tests, and the opt-in 10,000-flow benchmark. Record UI/headless limitations rather than claiming unverified behavior.
- **Anti-masking**: PASS. Invalid, blocked, capacity-limited, and rounded-to-zero flows receive explicit inspectable outcomes; exceptions are not silently swallowed.

## Research and Design Outputs

- [research.md](research.md) records codebase findings and design decisions.
- [data-model.md](data-model.md) defines persistent policy, flow, and signal records.
- [contracts/migration-contracts.md](contracts/migration-contracts.md) defines action, event, policy, and system interfaces.
- [quickstart.md](quickstart.md) gives reproducible test and benchmark commands.

## Project Structure

### Documentation (this feature)

```text
specs/107-migration-and-border-mobility/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── migration-contracts.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/shared/
├── actions.py                         # Extend existing migration-policy action compatibly
└── events.py                          # Durable migration lifecycle/political-signal events

modules/base/
├── registration.py                    # Register the migration system
├── schema.py                          # Typed migration policy/transition/flow/signal tables
└── systems/
    ├── demographics/
    │   ├── migration_policy.py         # Pure deterministic eligibility, capacity, and cohort rules
    │   └── migration_system.py         # Effective policy, flow lifecycle, population, and signals
    ├── politics/politics_system.py     # Consume bounded migration political pressure
    └── world/
        ├── bootstrap_system.py         # Seed default effective policy without replacing legacy laws
        └── ai/
            └── migration_policy.py     # Select policy through the existing AI framework

src/client/ui/
├── layouts/game_panel_registry.py     # Register the migration panel
└── panels/
    ├── migration_presenter.py          # Read-only country/region migration summary
    └── migration_panel.py              # Passive view and semantic policy actions

tests/
├── test_migration_policy.py
├── test_migration_system.py
├── test_migration_integration.py
├── test_migration_ai_policy.py
├── test_migration_presenter.py
└── test_migration_performance.py
```

**Structure Decision**: Extend the existing single Python application and base gameplay module. Keep calculations as reusable policy functions, store durable state in schema-registered tables, expose player intent only as `GameAction`, and put the UI read model in the client. Do not create a new engine, persistence, or population subsystem.

## Complexity Tracking

No constitution violations or additional project layers are proposed.
