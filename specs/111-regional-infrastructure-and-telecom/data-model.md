# Data Model: Regional Infrastructure and Telecommunications

## Authoritative profile

Stored in `regional_infrastructure`, keyed by `(region_id, category)`.

| Field | Type | Meaning |
|---|---|---|
| `region_id` | Int32 | Existing authoritative region ID. |
| `category` | Utf8 | Configured category. Built-ins are `transport`, `utilities`, `industrial`, and `telecom`; scenarios may add a category by supplying a complete policy. |
| `level` | Float64 | Developed category level, clamped to `[0, maximum]`. |
| `condition` | Float64 | Service condition, clamped to `[0, 1]`. |
| `capacity` | Float64 | Derived operating capacity: `clamp(level / maximum, 0, 1) * condition`. |
| `baseline` | Float64 | Configured initial level used when no legacy regional value is available. |
| `maximum` | Float64 | Configured construction ceiling. |
| `maintenance_level` | Float64 | Last resolved maintenance allocation ratio, bounded to `[0, 1]`. |
| `maintenance_cost_per_level_month` | Float64 | Scenario cost rate used to present category maintenance need. |
| `last_change_minute` | Int64 | Game-time minute of the last profile change. |
| `last_source_type` | Utf8 | `baseline`, `legacy`, `project`, or `depreciation`/damage source type. |
| `last_source_id` | Utf8 | Stable project, impact, event, or game-minute identifier. |

Category policy configuration supplies `baseline`, `maximum`, `construction_cost_per_level`, `construction_minutes_per_level`, `maintenance_cost_per_level_month`, and `annual_depreciation`. Optional `legacy_level_column`, `legacy_condition_column`, and a `damage_response` mapping customize legacy seeding and damage multipliers. A new category must supply all six numeric values; all configured values must be finite and within their policy bounds.

## Project lifecycle

Stored in `infrastructure_projects`, keyed by `id`.

| Field | Type | Meaning |
|---|---|---|
| `id` | Utf8 | Deterministic project identifier. |
| `country_id` | Utf8 | Funding country and required current regional owner. |
| `player_id` | Utf8 | Actor that authorized the project; cancellation is limited to this actor. |
| `region_id` | Int32 | Region receiving the project. |
| `category` | Utf8 | Configured infrastructure category. |
| `project_type` | Utf8 | `upgrade` changes developed level; `repair` restores capacity/condition. |
| `funding_source` | Utf8 | Currently `treasury`; cost is reserved from the country treasury at acceptance. |
| `start_level` | Float64 | Starting level for upgrades or starting capacity for repairs. |
| `target_level` | Float64 | Upgrade level, or repair capacity target. |
| `progress` | Float64 | Deterministic completed share in `[0, 1]`. |
| `cost_total` | Float64 | Server-calculated total quoted cost. |
| `duration_minutes` | Int64 | Server-calculated construction duration in game minutes. |
| `started_at_minute` | Int64 | Game-time start. |
| `updated_at_minute` | Int64 | Game-time checkpoint used to advance progress. |
| `completed_at_minute` | Int64 | Completion minute, or zero while incomplete. |
| `status` | Utf8 | `in_progress`, `paused`, `completed`, or `cancelled`. |
| `reason` | Utf8 | Readable reason for the last lifecycle decision. |
| `restoration_ceiling` | Float64 | Repair ceiling copied from the applicable damage history/profile ceiling. |

Only one `in_progress` or `paused` project may target a `(region_id, category)` pair. Progress advances only on game time. Loss of regional control pauses the project without advancing it; regaining control resumes it. Cancellation refunds `cost_total * (1 - progress)` to the original funding country. Rejected actions do not mutate treasury or capacity.

## Damage history

Stored in `infrastructure_damage_records`, keyed by `id`.

| Field | Type | Meaning |
|---|---|---|
| `id` | Utf8 | Stable idempotency key containing source, region, and category. |
| `source_id` | Utf8 | Original impact/event identifier. |
| `source_type` | Utf8 | `strategic` or `disaster`. |
| `region_id` | Int32 | Affected region. |
| `category` | Utf8 | Affected configured category. |
| `severity` | Float64 | Applied bounded condition-loss ratio. |
| `pre_damage_level` | Float64 | Developed level before the damage. |
| `pre_damage_condition` | Float64 | Condition before the damage. |
| `restoration_ceiling` | Float64 | Capacity immediately before damage; repairs cannot exceed the effective ceiling. |
| `damaged_at_minute` | Int64 | Game-time damage timestamp. |
| `recovered` | Boolean | Whether a completed repair has reached this record's restoration ceiling. |

Damage sources are sorted deterministically and applied once. Built-in strategic and disaster mappings can be customized through each category's `damage_response` policy. The record retains the causal attribution after recovery.

## Materialized read models

`regional_infrastructure` is authoritative. The system publishes bounded values on existing tables for current consumers:

- `regions.transport_access`, `utilities_capacity`, `industrial_access`, and `telecom_capacity` expose the matching category capacities.
- `regions.infrastructure` aliases transport capacity; `communications` aliases telecom capacity; `health_capacity` aliases utilities capacity.
- `regions.infrastructure_health` is the mean condition across configured profile categories for the region.
- Country fields `infrastructure_index`, `telecom_index`, `public_service_index`, and `industrial_access_index` are category-capacity aggregates weighted by population, then total population, then available age cohorts, then region area. An all-zero weight produces zero.

The system compares projected outputs with their current materialized values and writes only changed regional/country rows. Derived values remain recomputable from profile rows and never create production, population, ownership, or budget by themselves.

## Persistence and migration

The base schema registry supplies missing support tables and defaults for partial legacy tables. Existing regional infrastructure/communications values seed profiles where configured legacy columns exist; otherwise the policy baseline is used. Seeding does not debit treasury or change existing national totals. Generic Arrow snapshots and save/load persist profile, project, damage, and game-time state without custom serializers.
