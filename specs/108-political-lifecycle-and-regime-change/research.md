# Research: Political Lifecycle and Regime Change

## Existing architecture

- `modules/base/systems/politics/politics_system.py` applies weekly stability drift and consumes published migration-pressure and random-event approval effects. It is registered as a base gameplay system.
- Country runtime schema already separates `gvt_approval`, `gvt_stability`, and `gvt_corruption`; legacy government and law catalogs exist as scenario data.
- Authoritative user actions use shared dataclasses, system-side authorization, ordered simulation processing, and journaled results. AI modules can submit through the same action path.
- Save state is table-oriented. `modules/base/schema.py` supplies defaults for legacy saves; snapshot IPC serializes tables without a separate political persistence service.
- The treaty/politics UI reads presenter projections from client snapshots and dispatches actions; it does not mutate simulation state.

## Decisions

### Decision: Store lifecycle state in dedicated keyed tables

Government forms, parties, active law transitions, elections, crisis cases, and cause records have distinct identity and lifetimes. Keep those records separate rather than adding lists/JSON blobs to `countries`; retain current country columns as synchronized headline values for existing consumers.

**Rationale**: Supports deterministic updates, schema validation, snapshot/save compatibility, and incremental indexes without replacing the current data model.

**Alternatives considered**: A single JSON column per country was rejected because it weakens schema validation, queryability, migration behavior, and high-volume updates.

### Decision: Use explicit data-driven rules and safe legacy defaults

Government form and law seed rows remain the starting catalog. Missing lifecycle metadata is derived once into a valid initial state. Electoral interval defaults to four game years only where no form/scenario value exists; non-electoral forms remain unscheduled.

**Rationale**: Keeps existing scenarios playable and avoids a competing static catalog.

**Alternatives considered**: Hard-coding country-specific elections was rejected because it duplicates scenario policy and prevents mods from defining institutions.

### Decision: Make one deterministic political update authoritative

Actions are validated and recorded by the political system. Due transitions are resolved in a documented order using game minutes, sorted stable IDs, and integer/decimal arithmetic with clamps. AI chooses actions but does not receive bypass access.

**Rationale**: Provides replay consistency and makes authority checks identical for human and AI behavior.

### Decision: Publish effects rather than duplicate dependent formulas

Resolved laws and crises produce bounded, typed political effect records and attributable cause/history rows. Existing economy, migration, military, diplomacy, and stability systems consume only effects they own.

**Rationale**: Preserves the existing subsystem calculations and strict module boundaries.

### Decision: Preserve prior regime state on failed transitions

A failed or rejected coup/transition updates the crisis outcome and political consequences only; government, ruling authority, and laws change together only on a successful resolution boundary.

**Rationale**: Satisfies atomic regime changes and avoids partially applied political state.

## Unknowns and risks resolved

- No additional dependency or external service is needed.
- Exact historical election rules are scenario data; initial generic formulas are deterministic and inspectable.
- Existing country-only macro indicators cannot attribute causes to individual laws unless an effect/cause record is explicitly emitted. The system must report unknown attribution rather than infer it.
- The seed data's schema and rule coverage must be audited during implementation; missing government form metadata uses explicit defaults and is covered by tests.
