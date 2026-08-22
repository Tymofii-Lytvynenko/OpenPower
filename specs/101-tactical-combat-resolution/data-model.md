# Data Model: Tactical Combat Resolution MVP

All tables are Polars `DataFrame` values owned by `GameState`. String enums are lowercase on the wire (`parked`, `ready`, `fortified`); UI labels may title-case them. Every table has a deterministic key listed below.

## Unit readiness fields

The existing `units` table remains the canonical unit record. Add these columns:

| Field | Type | Default | Invariant |
|-------|------|---------|-----------|
| `readiness_status` | `Utf8` | `parked` for newly deployed units | One of `parked`, `ready`, `fortified`; this is the last completed status. |
| `readiness_transition_id` | `Utf8` | `""` | Empty when no transition is active; otherwise references `unit_readiness_transitions.id`. |
| `readiness_progress` | `Float64` | `0.0` | Clamped to `[0.0, 1.0]`; a view cache derived from transition timestamps. |
| `readiness_eta_minute` | `Int64` | `0` | Authoritative simulation minute at completion, or `0` when no transition is active. Clients derive remaining time from this value and the current game minute. |

Existing movement and engagement columns remain unchanged. A unit cannot have two active transition rows. Newly deployed units are created as `parked`. For backward compatibility, a loaded save that predates this feature fills the missing column with `ready` so existing formations are not unexpectedly immobilized; invalid values normalize to `ready`.

## `unit_readiness_transitions`

Key: `id` (one active row per `unit_id`).

| Field | Type | Description |
|-------|------|-------------|
| `id` | `Utf8` | Stable transition identifier, deterministic from unit and start minute. |
| `unit_id` | `Utf8` | Foreign key to `units.id`. |
| `from_status` | `Utf8` | Stable status at transition start. |
| `target_status` | `Utf8` | Requested final status. |
| `stage` | `Utf8` | `direct`, `parked_to_ready`, `parked_to_fortified`, or `ready_to_fortified`; `parked -> fortified` reuses the active row for two ordered stages. |
| `started_at_minute` | `Int64` | Inclusive simulation start time. |
| `completes_at_minute` | `Int64` | Exclusive completion boundary. |
| `progress` | `Float64` | Server-updated cache for snapshot consumers. |
| `pending_order_id` | `Utf8` | Optional order released after successful completion. |

Invariants:

- `completes_at_minute >= started_at_minute` and progress is monotonic while time advances.
- A zero-duration transition completes in the same server update and emits no intermediate progress frame.
- Completion atomically updates `units.readiness_status`, removes the active row, and either starts the next ordered stage or releases the pending order.
- Paused simulation leaves both timestamps and progress unchanged.

## `unit_pending_orders`

Key: `id`.

This normalized table persists orders that must wait for readiness. It avoids embedding arbitrary dictionaries in a Polars cell.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `Utf8` | Stable order identifier. |
| `unit_id` | `Utf8` | Foreign key to `units.id`. |
| `order_type` | `Utf8` | `move` or `attack`. |
| `target_region_id` | `Int32` | Move destination, `0` for attack orders. |
| `target_latitude` | `Float64` | Optional move coordinate, default `0.0`. |
| `target_longitude` | `Float64` | Optional move coordinate, default `0.0`. |
| `target_unit_id` | `Utf8` | Attack target, empty for move orders. |
| `via_region_ids` | `List[Int32]` | Existing direct-route waypoints. |
| `created_at_minute` | `Int64` | Ordering and replay boundary. |
| `status` | `Utf8` | `queued`, `released`, `canceled`, or `rejected`. |

Only one queued order is allowed per unit. Releasing an order deletes or marks the row as `released` after the original action is applied, preserving an audit-friendly deterministic event sequence.

## `battles`

Key: `id`; existing columns are retained for compatibility.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `Utf8` | — | Deterministic `battle-region-{region_id}-{war_id}` identifier. |
| `war_id` | `Utf8` | `""` | Active war context. |
| `region_id` | `Int32` | `0` | Region where stationary contact exists. |
| `attacker_side` | `Utf8` | `""` | Comma-separated sorted country IDs for compatibility; mirrors `SIDE_A`. |
| `defender_side` | `Utf8` | `""` | Comma-separated sorted country IDs for compatibility; mirrors `SIDE_B`. |
| `mode` | `Utf8` | `positional` | Existing `positional` or `assault` mode. |
| `status` | `Utf8` | `active` | `active`, `stalemate`, or `concluded`. |
| `balance` | `Float64` | `0.0` | `SIDE_A` share of weighted active strength. |
| `side_a_strength` | `Float64` | `0.0` | Weighted effective strength. |
| `side_b_strength` | `Float64` | `0.0` | Weighted effective strength. |
| `side_a_losses` | `Int64` | `0` | Cumulative losses in the current battle. |
| `side_b_losses` | `Int64` | `0` | Cumulative losses in the current battle. |
| `round` | `Int32` | `0` | Number of completed combat rounds. |
| `started_at_minute` | `Int64` | `0` | Battle start time. |
| `updated_at_minute` | `Int64` | `0` | Last status/strength update. |
| `concluded_at_minute` | `Int64` | `0` | Set only when status becomes `concluded`. |
| `victor_side` | `Utf8` | `""` | `SIDE_A`, `SIDE_B`, or empty until conclusion. |

Exactly two aggregate sides are permitted. `balance` and strengths are recomputed from participant rows after any combat round; stable sorting by country and unit ID makes replay output deterministic.

## `battle_participants`

Key: (`battle_id`, `country_id`).

| Field | Type | Description |
|-------|------|-------------|
| `battle_id` | `Utf8` | Foreign key to `battles.id`. |
| `country_id` | `Utf8` | Participating country. |
| `side` | `Utf8` | `SIDE_A` or `SIDE_B`; no third value. |
| `role` | `Utf8` | `principal` for war-side members or `ally` for eligible support. |
| `eligibility_basis` | `Utf8` | `war_side` or `military_alliance`. |
| `unit_count` | `Int32` | Number of stationary units contributing. |
| `weighted_strength` | `Float64` | Sum of effective unit strengths. |

An ally is included only when the active treaty/wartime relationship is valid and at least one eligible unit is physically present. Neutral countries are omitted, not assigned a third side.

## `battle_units`

Key: (`battle_id`, `unit_id`); existing fields are retained and extended:

| Field | Type | Description |
|-------|------|-------------|
| `battle_id` | `Utf8` | Foreign key to `battles.id`. |
| `unit_id` | `Utf8` | Foreign key to `units.id`. |
| `country_id` | `Utf8` | Owning country. |
| `side` | `Utf8` | `SIDE_A` or `SIDE_B`. |
| `role` | `Utf8` | `principal` or `ally`. |
| `readiness_status` | `Utf8` | Stable status used for this tick. |
| `contribution_weight` | `Float64` | `0.25`, `1.0`, or `1.5` according to status and stationary posture. |
| `effective_strength` | `Float64` | Raw strength multiplied by contribution weight. |
| `strength_share` | `Float64` | Effective share of both sides, retained for existing consumers. |

## `occupations`

Key: `region_id`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `region_id` | `Int32` | `0` | Region under military control. |
| `controller_country_id` | `Utf8` | `""` | Winning side's selected controller. |
| `garrison_strength` | `Int64` | `0` | Surviving friendly strength assigned to the occupation. |
| `resistance` | `Float64` | `0.0` | Reserved MVP occupation resistance value, updated only by occupation policy. |
| `occupation_status` | `Utf8` | `active` | `active` or `ended`. |
| `started_at_minute` | `Int64` | `0` | First victory/control time. |
| `updated_at_minute` | `Int64` | `0` | Last controller/status update. |
| `contested` | `Boolean` | `False` | Whether another hostile force is currently contesting the region. |

`regions.controller` remains the fast lookup and is updated in the same authoritative transaction. `regions.owner` is never changed by this feature.

## Shared view projection

`BattleStatusView` is a read-only projection, not a persisted table. It contains:

```text
battle_id, region_id, status, mode, round, side_a_countries, side_b_countries,
side_a_strength, side_b_strength, balance, victor_side,
started_at_minute, updated_at_minute, concluded_at_minute,
participants, readiness_distribution, occupation
```

`UnitReadinessView` similarly exposes `unit_id`, `readiness_status`, `transition_target`, `progress`, `eta_minute`, and `remaining_minutes`. `remaining_minutes` is derived as `max(0, eta_minute - current_game_minute)` when a transition is active and is never persisted as a second countdown. Both projections are built from snapshot tables and never write back to `GameState`.

## Migration and compatibility

Older saves receive additive defaults for all new columns/tables through the server-owned migration boundary. Existing `attacker_side`, `defender_side`, `status`, and `strength_share` fields remain populated so current panels and tests continue to work. Event consumers continue to receive `EventBattleStarted` and `EventBattleEnded`; new update/conclusion/diagnostic payloads are additive and use the same battle IDs. Occupation `resistance` is initialized and retained as `0.0`; no resistance progression is simulated.
