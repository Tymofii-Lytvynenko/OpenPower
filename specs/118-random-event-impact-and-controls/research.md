# Research: Random Event Impact and Controls

## Decision: Extend the existing event system instead of adding a second generator

`modules/base/systems/world/random_events_system.py` is the registered daily roll and is already ordered after the clock. It selects one of ten event types, stores active placards in `state.globals["active_events"]`, and emits `EventRandomEventTriggered`. Keep this as the only trigger source and evolve its lifecycle in place.

**Rationale**: The specification explicitly bounds this feature as an extension. A second generator would create duplicate rolls, conflicting cooldowns, and non-deterministic ordering.

**Alternatives considered**: A separate event scheduler; rejected because it would duplicate existing trigger state and make compatibility and deterministic replay harder.

## Decision: Store scalable authoritative event records in Polars tables

The schema registry in `modules/base/schema.py` owns gameplay tables. The save writer serializes all `GameState.tables`; the snapshot encoder copies all tables and determinism state. Add typed tables for event instances, event effects, and responses. Keep only compact scenario-wide control defaults in `GameState.globals` and materialize category controls as table rows.

**Rationale**: This follows the repository's data-oriented state contract and supports due-row processing and the 10k/100k benchmark. Snapshot support is generic, so the records require no engine/server serialization special case.

**Alternatives considered**: Store every event/effect as nested dictionaries in globals; rejected for poor validation, large-state scans, and divergence from the authoritative schema contract.

## Decision: Reuse `DeterministicRuntime`, actions, and domain journal

`DeterministicRuntime` persists RNG state and ID allocation in `GameState.determinism`. Systems receive commands via `GameState.current_actions`, with declared `SystemAccess.handles`. Domain events are captured into the existing journal and both events and state tables are snapshot-persisted. Event responses use a shared action; lifecycle transitions use shared domain events and existing command-result records.

**Rationale**: This produces replayable outcomes and preserves the client/server IPC boundary.

**Alternatives considered**: Python's process-randomized `hash()` or the global `random` module; rejected because they do not provide stable replay across runs.

## Decision: Reuse downstream domain systems for effects

Infrastructure already consumes `EventRandomEventTriggered` and produces attributed, bounded damage records. Expand effects through explicit effect records and domain-specific consumers/policies; do not make the event system a second population, economic, health, budget, migration, or political simulator.

**Rationale**: The existing domains own their state transitions and bounds, and their system ordering is part of the authoritative simulation contract.

**Alternatives considered**: Mutate every domain table directly from the event trigger; rejected because it bypasses domain validation and creates policy coupling.

## Decision: Preserve legacy event state during migration

On first update after schema initialization, import well-formed legacy `active_events` records into the new instance table using their existing IDs, type, region, severity, start, and expiry. Infer only documented catalog defaults for missing fields. Keep the legacy list as a compatibility projection while the existing renderer/feed still consumes it; new table state is authoritative.

**Rationale**: Existing saves and read-only client code must remain usable while the new event lifecycle lands incrementally.

**Alternatives considered**: Drop the old field or reinterpret incomplete legacy rows as fully known; rejected because either loses active play state or invents unsupported event history.

## Repository facts checked

- `modules/base/registration.py` registers `RandomEventsSystem`.
- `InfrastructureSystem._apply_damage` already turns triggered disasters into infrastructure damage records with stable source IDs.
- `src/shared/snapshots.py` copies all tables, globals, determinism state, and events; save loading uses module schema migrations.
- `EventFeedPresenter` reads the legacy active-event projection and existing news table; it can be extended without importing module code.
- The current catalog has ten types and a hard-coded daily chance, active cap, duration, and severity range; it does not implement scenario/category controls, responses, or effect/history tables.
