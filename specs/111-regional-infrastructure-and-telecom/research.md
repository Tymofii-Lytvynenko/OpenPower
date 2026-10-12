# Research: Regional Infrastructure and Telecommunications

## Decision: Keep infrastructure policy in the base gameplay module

**Decision**: Implement category rules and project lifecycle as composable `ISystem` policy under `modules/base/systems/world/`.

**Rationale**: The repository registers gameplay systems through the base module; the engine remains content-agnostic. Military movement and strategic warfare already consume or modify regional infrastructure-like fields.

**Alternatives considered**: Add infrastructure rules to `src/engine` or `src/server`. Rejected because those layers must not own game-specific policy.

## Decision: Store category profiles in a keyed long-form Polars table

**Decision**: Use one `regional_infrastructure` row per `(region_id, category)` and separate tables for projects and source-attributed damage. Derive aggregate columns for existing systems.

**Rationale**: The specification requires configurable categories and category-specific level, condition, and capacity. A long-form table permits new categories without continually expanding the region schema, while materialized columns preserve compatibility with existing route and impact consumers.

**Alternatives considered**: Add four groups of fields directly to every region. Rejected because data-schema growth would be category-specific and hard to extend. Store profiles in `GameState.globals`. Rejected because nested dictionaries lose typed Polars/Arrow contracts and efficient vectorized updates.

## Decision: Preserve legacy values and seed only additive profile state

**Decision**: If a legacy region already has supported infrastructure or communications values, initialize matching profiles from those values. For absent categories, use explicit scenario-configurable defaults. Do not modify ownership, population, treasury, or national GDP during profile initialization.

**Rationale**: The feature assumptions require backward-compatible baselines and no unexplained change to existing national totals.

**Alternatives considered**: Reset all regions to one default or infer capacity from national spending. Rejected because either would discard existing state or manufacture national indicators.

## Decision: Use deterministic game time and atomic project funding

**Decision**: Project progress and depreciation advance at the game-time boundary. Validate the entire investment before debiting treasury; record its funding source, cost, target, progress, and status in persistent tables.

**Rationale**: This matches deterministic simulation/replay and avoids partial spending on rejected actions. Existing command sequencing and finite-payload validation remain authoritative.

**Alternatives considered**: Progress using client frame delta or real wall time. Rejected because it would diverge across clients/replays. Debit incrementally without reserving funds. Rejected because later ticks could create an underfunded project.

## Decision: Make damage idempotent and reconstruction bounded

**Decision**: Attribute each damage record to a source identifier and category. Ignore duplicate source records and cap reconstruction by the stored pre-damage ceiling or configured baseline.

**Rationale**: Strategic impacts can be observed repeatedly through snapshots or save/load; source keys prevent double damage, and recovery cannot silently exceed the prior state.

**Alternatives considered**: Recompute damage from all historical strategic impacts every tick. Rejected because it is expensive and re-applies old impacts. Keep only a single latest damage value. Rejected because it loses cause/history and cannot enforce recovery bounds.

## Decision: Reuse existing downstream contracts through bounded modifiers

**Decision**: Materialize normalized regional transport, utility/service, industrial, and telecom modifiers, then update existing consumers at their current boundaries. National aggregates use population weights, then total population, age cohorts, and area as available fallbacks.

**Rationale**: The feature explicitly extends movement, production, development, intelligence, and strategic damage rather than replacing them. Bounded materialized modifiers avoid repeated policy reimplementation in each consumer.

**Alternatives considered**: Add separate infrastructure formulas to each consumer. Rejected because it would duplicate mechanics and produce inconsistent values. Use only national averages. Rejected because the requirement prohibits dependent systems from inferring regional condition from a national average.

## Decision: Incremental and vectorized updates

**Decision**: Skip project, damage, and depreciation work when those inputs are not due; apply event damage only to affected categories; project broad profile and aggregate outputs with Polars, then write only rows whose materialized values changed. When there are no active projects or damage events, the equivalent depreciation refresh uses column expressions; the mutable row path remains for active records.

**Rationale**: The 100,000-category-record success criterion requires bounded work; Python pairwise region scans are not acceptable. The controlled benchmark confirms the incremental materialized-output path updates 1,000 changed profiles and 250 affected regional read models within the one-second limit.

**Alternatives considered**: Rebuild all profiles from source regions on every simulation tick. Rejected because it is unnecessary and violates the incremental-processing requirement.
