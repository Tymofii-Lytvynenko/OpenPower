# Implementation Plan: Regional Infrastructure and Telecommunications

**Branch**: `111-regional-infrastructure-and-telecom` | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/111-regional-infrastructure-and-telecom/spec.md`

## Summary

Add authoritative, region-level infrastructure profiles, funded projects, maintenance/depreciation, and source-attributed damage. Keep infrastructure policy in the base gameplay module, use additive Polars tables for persistence/snapshot compatibility, and materialize bounded regional/national modifiers consumed by existing movement, production, development, and intelligence systems. Investments are submitted as server-validated actions; the client remains a passive presenter.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: Polars 1.36.1, existing `GameAction`/`ISystem` contracts, deterministic game clock, schema registry, Arrow snapshots, and existing military route and strategic-impact policies. No new runtime dependency.

**Storage**: Authoritative Polars tables: `regional_infrastructure` (one row per region/category), `infrastructure_projects`, and `infrastructure_damage_records`; aggregate compatibility fields are materialized on existing `regions` and `countries` tables. Save/load and snapshot compatibility use the existing generic schema and persistence paths.

**Testing**: pytest with focused policy/system/action tests, existing route/military/economy/layer-boundary regressions, and an isolated 100,000-record performance benchmark.

**Target Platform**: Existing desktop client and headless authoritative server.

**Project Type**: Python modular simulation engine and desktop client.

**Performance Goals**: Advance project and depreciation state only when due, process damage only for incoming impacts/events, use Polars for normalized profile/read-model projections, and write only changed regional/country rows. The 100,000 regional-category update gate is under one second when 1% of records changed.

**Constraints**: No new region ownership, population, production, budget, intelligence, or strategic-damage model. No client-side state mutation. Preserve legacy region fields and derive documented baselines without changing national totals during migration. Capacity and condition stay in `[0, 1]`; costs and damage are finite and non-negative.

**Scale/Scope**: Approximately 4,561 base regions, four initial infrastructure categories, and data-configurable additional categories; multiplayer transport remains a separate feature.

## Constitution Check

| Principle/gate | Pre-research result | Design result |
|---|---|---|
| Strict layer separation and passive client | Pass: actions and state remain shared contracts; policy belongs in `modules/base`; client reads snapshots. | Pass: infrastructure logic is an `ISystem`; presenters only build read models and dispatch actions. |
| Data-oriented schemas and Arrow compatibility | Pass: regions are already Polars and base-owned support tables use `BASE_TABLE_SCHEMAS`. | Pass: profiles/projects/damage are keyed Polars tables with generic snapshots and save/load. |
| Modular, reusable, SOLID design | Pass: current movement, budget, strategic, and client layers provide integration points. | Pass: category defaults/calculation, project lifecycle, and system orchestration are separate modules. |
| Professional comments and maintainability | Pass: documented user rules require English comments that explain rationale. | Pass: prefer descriptive names; comments only explain compatibility and non-obvious constraints. |
| Empirical verification and anti-masking | Pass: tests are required by the feature success criteria. | Pass: no silent fallback for invalid investments; tests assert rejection and conservation of funds/capacity. |

No constitutional violation or complexity exception is required.

## Implementation Design

### Phase 0 — research conclusions

See [research.md](research.md). The existing movement system already reads a regional `infrastructure` modifier, strategic warfare already changes supported regional infrastructure/communications fields, and the budget already exposes national infrastructure and telecom allocations. The design extends those contracts instead of adding parallel systems.

### Phase 1 — authoritative state and compatibility

1. Register `regional_infrastructure`, `infrastructure_projects`, and `infrastructure_damage_records` in `modules/base/schema.py` with stable primary keys and explicit defaults.
2. Add a small pure infrastructure policy module under `modules/base/systems/world/` for category profiles, bounded costs, capacity aggregation, project eligibility, damage, and reconstruction ceilings.
3. Add investment/cancellation `GameAction` contracts in `src/shared/actions.py`; all values are checked for finiteness by the existing command pipeline and country authority by the existing authorization validator.
4. Add `InfrastructureSystem` through `modules/base/registration.py`. It initializes profiles from existing region values when present, otherwise from configurable scenario defaults; it never edits ownership or population.
5. Seed only after region loading and schema normalization. Persist project progress and damage causes as tables so save/load, IPC snapshots, replay, and mod schema migration remain generic.

### Phase 1 — lifecycle and budget rules

1. On an investment action, require the current region owner to match the authorized country, category to be configured, target level to be finite and within the category maximum, no incompatible active project, and sufficient available reserves.
2. Quote and debit the full project cost atomically when accepted. Record funding source, owner, start, target, cost, duration, progress, status, and reason. A cancellation refunds only the still-uncommitted project amount according to the explicit policy; no partial debit is allowed for rejected requests.
3. Progress projects on the deterministic game-time boundary. Pause projects after loss of regional control; resume only when the original funding country regains control or an explicit transfer rule applies.
4. Apply condition depreciation and maintenance from configured use/age/maintenance terms. Use existing national `budget_infra_ratio`, `budget_telecom_ratio`, and `budget_health_ratio` as bounded maintenance inputs, with configurable wear for active occupation; never fabricate treasury funds.
5. Apply strategic/random-event damage by source and category, with a unique source key to avoid duplicate application after save/load. Repairs restore only the recorded damage ceiling or configured baseline.

### Phase 1 — dependent systems and read models

1. Materialize bounded regional modifiers (`infrastructure`, `infrastructure_health`, `communications`, transport, utilities, and industrial access) for current military and strategic consumers.
2. Publish area/population-weighted national aggregates on `countries` for compatibility. Empty or invalid regions do not create production or population.
3. Integrate bounded modifiers into military route duration/telecom coordination, production throughput, population health outcomes, and existing covert-information freshness without duplicating their base calculations.
4. Add a read-only regional presenter that reports category level/condition/capacity, active project, maintenance need, last source-attributed change, and national comparison. Keep rendering in client UI and commands in existing controller/session paths.
5. Add focused deterministic tests before implementation, then run the feature quickstart and regressions for military movement, strategic warfare, budget, state schemas, save/load, and layer boundaries.

## Project Structure

```text
specs/111-regional-infrastructure-and-telecom/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/infrastructure-actions.md
└── tasks.md

modules/base/
├── registration.py
├── schema.py
└── systems/world/
    ├── infrastructure_policy.py
    ├── infrastructure_system.py
    └── ai/infrastructure_policy.py

src/shared/actions.py
src/client/ui/panels/infrastructure_presenter.py
src/client/ui/panels/region_infrastructure_panel.py
tests/test_infrastructure_policy.py
tests/test_infrastructure_ai_policy.py
tests/test_regional_infrastructure_system.py
tests/test_infrastructure_presenter.py
tests/test_infrastructure_performance.py
```

**Structure Decision**: Continue the existing module/ECS organization. Shared actions contain only data contracts, base module systems own gameplay policy, the existing schema registry owns support tables, and the client adds read-only projection/presentation. No engine-loop or server-layer gameplay policy changes are planned.

## Complexity Tracking

No violations. The long-form category table avoids duplicating category-specific fields and makes additional configured categories additive; materialized columns are compatibility outputs for existing consumers, not a second source of truth.
