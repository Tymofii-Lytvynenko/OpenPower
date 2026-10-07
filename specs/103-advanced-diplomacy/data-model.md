# Data Model: Advanced Diplomacy & Coalition Systems

All persistent state lives in schema-managed `GameState.tables`; shared actions carry commands, and immutable shared events announce applied facts.

## Main tables

| Table | Key | Purpose |
|---|---|---|
| `peace_deals` | `id` | Structured multi-clause proposal, proposer, responding-side set, accepted responses, status, deadline, utility, and resolution reason. |
| `countries_wars` | `id` | Active belligerent sides/leaders, cause, and origin time used for validation and exhaustion. |
| `aggressive_expansion_events` | `id` | Time-bounded source/target/action records and threat deltas; expire after the configured rolling window. |
| `aggressive_expansion_scores` | `country_id` | Current bounded expansion score plus unprovoked-war/occupied-region counts. |
| `coalition_pacts` | `id` | Leader, members, primary target, mutual-defense flag, threat score, status, and lifecycle timestamps. |
| `war_exhaustion_states` | `id` | Per-war/per-country index, rate, stability/efficiency penalties, peace desire, casualty/occupation/blockade/duration inputs. |
| `countries_treaties` | `id` | Existing alliances, economic treaties, and status/membership used by validation and utility. |
| `countries`, `regions`, `units` | existing keys | UI/combat/political projections for exhaustion, expansion, coalition count, ownership/control, and demilitarized strength. `countries.diplomatic_ai_archetype` is optional content (`conciliatory`, `pragmatic`, `hawkish`) and defaults to neutral `pragmatic`. |

## Commands and events

- Commands: `ActionSubmitPeaceDeal`, `ActionRespondPeaceDeal`, and backward-compatible `ActionOfferPeace` handling.
- Peace events: `EventPeaceDealProposed`, `EventPeaceDealResolved`.
- Balance events: `EventAggressiveExpansionUpdated`, `EventCoalitionChanged`, `EventWarExhaustionUpdated`.
- Ownership facts: `EventTerritoryOwnershipChanged` emitted after ownership mutations commit; consumer logic must handle either active war side as attacker.

## State transitions

1. Validate command permissions and clause package; create deterministic pending deal id and emit proposal event.
2. Gather each required response; reject/expire immediately on a terminal response/deadline.
3. After unanimous acceptance, revalidate war and clauses, commit the package, emit territory facts, mark deal accepted, and enqueue existing peace actions to close the war.
4. On war/occupation/territory/day events, update one-year expansion records, threat projections, defensive pacts, and map events.
5. On battle/occupation/blockade/war/day events, recompute per-war exhaustion and derive country stability, peace-demand, and unit-efficiency projections.

## Invariants

- A deal has at most one terminal status transition; no clause is applied before unanimous required consent and final revalidation.
- Clause participants/targets must exist and satisfy the war-side rules; duplicate conflicting targets are rejected.
- Coalition membership is derived from active pacts, and pacts dissolve when the primary threat no longer has active wars/occupations or its force collapses.
- Exhaustion index, peace desire, scores, and penalties stay in their documented bounds; inactive wars do not retain active per-war exhaustion rows.
- Writes pass through `GameState.update_table` and preserve schema types/defaults for save/load and IPC.
