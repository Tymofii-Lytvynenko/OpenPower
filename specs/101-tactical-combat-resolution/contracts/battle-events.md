# Contract: Battle Lifecycle and Events

## Battle identity and side model

`battle_id` is deterministic for the active `(region_id, war_id)` pair. Every battle has exactly two aggregate sides:

```text
SIDE_A
SIDE_B
```

Each side may contain one or more countries. A country is assigned once and cannot appear on both sides. Country ordering in payloads is lexicographically sorted; participant and unit ordering follows the same rule.

For contact detected in an engagement zone before units share a region, `region_id` is the lowest positive `current_region_id` among contact units, with unit ID as the tie-breaker. Moving units do not contribute until stationary in that anchor region.

An eligible ally must have a direct active military or defensive alliance with a country already on the side, be present with a stationary unit in the battle region, and not be neutral to the opposing side. Alliance chains are not transitive. An ineligible or ambiguous ally is omitted for that update and produces a diagnostic rejection event; the server never creates a third side to represent it.

## Authoritative battle row

The `battles` row exposes:

```text
battle_id, war_id, region_id, mode, status,
attacker_side, defender_side,
round,
side_a_strength, side_b_strength, balance,
side_a_losses, side_b_losses,
started_at_minute, updated_at_minute, concluded_at_minute,
victor_side
```

`attacker_side` and `defender_side` remain compatibility aliases for `SIDE_A` and `SIDE_B`. Status values are `active`, `stalemate`, and `concluded`.

## Events

### `EventBattleStarted`

Emitted once when a battle ID first becomes active:

```text
battle_id: str
region_id: int
war_id: str
side_a_countries: list[str]
side_b_countries: list[str]
started_at_minute: int
```

Existing consumers that only accept `battle_id` and `region_id` remain valid through defaulted/additive fields.

### `EventBattleUpdated`

Emitted when any status, side membership, weighted strength, balance, losses, or mode value changes:

```text
battle_id: str
region_id: int
status: str
round: int
side_a_countries: list[str]
side_b_countries: list[str]
side_a_strength: float
side_b_strength: float
balance: float
updated_at_minute: int
```

No update event is emitted for an identical canonical row. A status transition from `active` to `stalemate` is an update, not a new battle.

### `EventBattleParticipantRejected`

Emitted when a physically present country cannot be assigned unambiguously:

```text
battle_id: str
country_id: str
reason: no_direct_alliance | ambiguous_side | no_stationary_presence
at_minute: int
```

This diagnostic event does not add a participant or change either aggregate side.

### `EventBattleEnded`

This existing event remains the compatibility conclusion event:

```text
battle_id: str
victor_tag: str
victor_side: str
region_id: int
concluded_at_minute: int
```

The row is marked `concluded` and the event is emitted once before the battle is retired from the active battle table. `victor_tag` is the deterministic dominant country on the winning side and does not change political ownership.

## Round and lifecycle rules

1. Contact creates a battle only when both sides have eligible stationary strength.
2. A round is resolved on the existing combat cadence; its input is aggregate effective strength weighted by stable unit readiness.
3. If both sides remain positive and the latest round changed no strength, status is `stalemate`; otherwise it is `active`. A later round that changes strength returns `stalemate` to `active`.
4. If one side reaches zero, status becomes `concluded`, zero-strength units are removed, the winning side is stored, and occupation/controller update occurs in the same authoritative state update.
5. If both sides reach zero in one round, status becomes `concluded` with no victor, no occupation/controller transfer, and a contested region.
6. A battle start, update, diagnostic, and conclusion event sequence is deterministic and sorted by battle ID when multiple regions update in one tick.

## Snapshot and replay guarantees

Events are transient notifications; `battles`, `battle_participants`, `battle_units`, `regions.controller`, and `occupations` are the replayable state. Replaying identical snapshots and actions yields identical rows and event payloads. Saving during an active battle preserves status, participant membership, strengths, timestamps, and the next resolution boundary.
