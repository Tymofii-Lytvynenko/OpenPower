# Data Model: Geo-Coordinated Military Movement

Movement state is held in Polars tables owned by `GameState`. The schema registry in `modules/base/schema.py` remains authoritative for persisted table columns and migrations.

## Unit movement fields (`units`)

| Field | Type | Purpose |
|---|---|---|
| `id` | Utf8 | Stable unit identifier |
| `owner` | Utf8 | Owning country tag |
| `unit_type` / `unit_domain` | Utf8 | Role and movement-domain policy inputs |
| `strength` | Int64 | Force size used by movement modifiers and combat |
| `current_region_id` | Int32 | Current political region; zero is used while off-map in deployment transit |
| `latitude` / `longitude` | Float64 | Current displayed geographic position |
| `source_region_id` | Int32 | Current segment origin |
| `source_latitude` / `source_longitude` | Float64 | Segment origin coordinate |
| `target_region_id` | Int32 | Current segment destination; non-positive means no target |
| `target_latitude` / `target_longitude` | Float64 | Segment destination coordinate |
| `departed_at_minute` / `arrival_at_minute` | Int64 | Authoritative segment timestamps |
| `movement_progress` | Float64 | Clamped normalized segment progress |
| `is_moving` | Boolean | Whether the unit has an active movement segment |
| `readiness_status` and transition fields | Utf8/Float64/Int64 | Readiness state; movement orders must respect its transitions |

## Accepted routes (`unit_movement_routes`)

Primary key: `unit_id`.

| Field | Type | Purpose |
|---|---|---|
| `unit_id`, `owner_country_id` | Utf8 | Unit and owner association |
| `source_region_id`, `destination_region_id` | Int32 | Route endpoints |
| `route_region_ids` | List[Int32] | Deterministic ordered region path |
| `route_index` | Int32 | Current route leg/waypoint cursor |
| `destination_latitude`, `destination_longitude` | Float64 | Final/custom target coordinate |
| `has_custom_destination`, `is_naval_invasion` | Boolean | Order behavior flags |
| `status`, `rejection_reason` | Utf8 | Planned/transit/arrived/blocked/interrupted status and explanation |
| `updated_at_minute` | Int64 | Last authoritative route update time |

## Order feedback (`unit_order_feedback`)

Primary key: `id`. Records `unit_id`, `owner_country_id`, `order_type`, `status`, `reason`, and `created_at_minute`. The military system retains a bounded recent history for client presentation.

## Route inputs

- `regions`: region IDs, owners/controllers, geographic center coordinates, and optional water/port/coastal/domain metadata.
- `region_adjacency`: undirected political-region connections; normalized by the route planner.
- `countries_wars` and `treaty_effects`: hostile relationships and transit/stationing permissions.
- `unit_readiness_transitions` and `unit_pending_orders`: queued posture/order state.
- `countries`: military count, money reserves, and derived `total_core_manpower`.
- `GameState.globals`: bounded scenario modifiers for domain, force size, infrastructure, telecom coordination, domestic/foreign territory, and invasion radii/types.

## State transitions

1. A valid order is resolved to a destination coordinate and legal deterministic route.
2. Readiness either authorizes departure or queues the order until its transition completes.
3. Each leg stores its departure/arrival minute and updates normalized progress.
4. On reaching a waypoint, access and domain policy are rechecked before the next leg begins.
5. At a naval-invasion landing boundary, escort and hostile-fleet conditions are re-evaluated before the unit is placed at the destination.
6. Invalid/rejected orders leave coordinates, readiness, and ownership unchanged and produce order feedback.
