# Data Model: Migration and Border Mobility

## Authoritative population

`regions.pop_14`, `regions.pop_15_64`, and `regions.pop_65` remain non-negative integer cohorts and the only source of population totals. A migration flow is authorization/history; it does not reserve or create a second population balance. Pending rows reserve source cohorts and destination capacity through aggregation at evaluation time. Completion subtracts and adds the exact same integer cohort vector in one system update.

## Persistent tables

### `migration_policies` — one active row per country

| Field | Type | Default | Meaning |
|---|---|---|---|
| `country_id` | Utf8 | `""` | ISO country key; primary key |
| `migration_policy` | Utf8 | `"managed"` | Legacy-compatible broad posture: `open`, `managed`, or `restricted` |
| `border_policy` | Utf8 | `"managed"` | Border posture: `open`, `managed`, or `closed` |
| `entry_rate` | Float64 | `0.5` | Share of eligible inflow admitted, in `[0, 1]` |
| `exit_rate` | Float64 | `0.5` | Share of eligible outflow permitted, in `[0, 1]` |
| `asylum_rate` | Float64 | `0.25` | Share of eligible displaced flow accepted, in `[0, 1]` |
| `family_reunification_rate` | Float64 | `0.5` | Eligible family flow multiplier, in `[0, 1]` |
| `skilled_worker_preference` | Float64 | `0.0` | Deterministic weighting of working-age/skilled cohort mix, in `[0, 1]` |
| `enforcement_strength` | Float64 | `0.5` | Restriction enforcement, in `[0, 1]` |
| `effective_at_minute` | Int64 | `0` | First game minute at which these values govern decisions |
| `updated_at_minute` | Int64 | `0` | Last accepted change |
| `source` | Utf8 | `"default"` | `default`, `player`, `ai`, or scenario provenance |

### `migration_policy_transitions` — scheduled future policy changes

| Field | Type | Default | Meaning |
|---|---|---|---|
| `id` | Utf8 | `""` | Deterministic unique transition key; primary key |
| `country_id` | Utf8 | `""` | Country whose policy will change |
| `migration_policy` | Utf8 | `"managed"` | Target broad posture |
| `border_policy` | Utf8 | `"managed"` | Target border posture |
| `entry_rate` | Float64 | `0.5` | Target admitted share |
| `exit_rate` | Float64 | `0.5` | Target permitted outflow share |
| `asylum_rate` | Float64 | `0.25` | Target asylum share |
| `family_reunification_rate` | Float64 | `0.5` | Target family multiplier |
| `skilled_worker_preference` | Float64 | `0.0` | Target working-age weighting |
| `enforcement_strength` | Float64 | `0.5` | Target enforcement strength |
| `requested_at_minute` | Int64 | `0` | Request time |
| `effective_at_minute` | Int64 | `0` | Scheduled activation boundary |
| `source` | Utf8 | `"player"` | `player`, `ai`, or scenario provenance |
| `status` | Utf8 | `"scheduled"` | `scheduled`, `applied`, or `cancelled` |
| `reason_code` | Utf8 | `""` | Stable transition result/rejection code |

### `migration_flows` — durable route lifecycle

| Field | Type | Default | Meaning |
|---|---|---|---|
| `id` | Utf8 | `""` | Deterministic unique flow key; primary key |
| `origin_region_id` | Int32 | `0` | Source region id |
| `destination_region_id` | Int32 | `0` | Destination region id |
| `origin_country_id` | Utf8 | `""` | Owner at authorization time |
| `destination_country_id` | Utf8 | `""` | Owner at authorization time |
| `dependent_count` | Int64 | `0` | Under-15 cohort |
| `working_age_count` | Int64 | `0` | Working-age cohort |
| `elderly_count` | Int64 | `0` | 65+ cohort |
| `population_count` | Int64 | `0` | Exact sum of the three cohorts |
| `reason_code` | Utf8 | `""` | Stable lifecycle/eligibility reason code |
| `reason_factors_json` | Utf8 | `"{}"` | Sorted compact JSON of bounded score factors and authorization basis |
| `created_at_minute` | Int64 | `0` | Flow request/evaluation time |
| `authorized_at_minute` | Int64 | `0` | Authorization boundary; zero for never-authorized results |
| `expected_completion_at_minute` | Int64 | `0` | Deterministic travel completion minute |
| `completed_at_minute` | Int64 | `0` | Actual completion minute; zero until completion |
| `transition_rule` | Utf8 | `"finish_authorized"` | Authorization-time rule for a subsequent border-policy change |
| `status` | Utf8 | `"pending"` | `pending`, `completed`, `redirected`, `rejected`, or `cancelled` |

Stable reason-code families: `eligible_domestic`, `eligible_mobility_agreement`, `border_closed`, `entry_restricted`, `exit_restricted`, `sanction_restricted`, `at_war`, `no_connection`, `no_destination_capacity`, `source_cohort_limit`, `rounded_to_zero`, `authority_changed`, `capacity_changed`, `border_changed`, `policy_changed`, and `redirected_capacity`.

### `migration_signals` — downstream current/windowed read model

| Field | Type | Default | Meaning |
|---|---|---|---|
| `country_id` | Utf8 | `""` | ISO country key; primary key |
| `gross_inflow` | Int64 | `0` | Completed inbound residents in the current signal window |
| `gross_outflow` | Int64 | `0` | Completed outbound residents in the current signal window |
| `net_flow` | Int64 | `0` | Inflow minus outflow |
| `working_age_delta` | Int64 | `0` | Net working-age cohort change |
| `service_pressure` | Float64 | `0.0` | Bounded incoming demand relative to service capacity, in `[0, 1]` |
| `political_pressure` | Float64 | `0.0` | Bounded sustained-flow signal for approval/stability/law pressure, in `[0, 1]` |
| `law_pressure` | Float64 | `0.0` | Bounded pressure on migration-law review, scaled by effective enforcement, in `[0, 1]` |
| `window_start_minute` | Int64 | `0` | Inclusive start of current aggregation window |
| `updated_at_minute` | Int64 | `0` | Last signal calculation |
| `politics_consumed_at_minute` | Int64 | `0` | Prevents applying one signal window repeatedly |
| `economy_consumed_at_minute` | Int64 | `0` | Consumer watermark for economic health |

## Relationships and invariants

- `migration_policies.country_id` and `migration_policy_transitions.country_id` reference `countries.id`.
- `migration_flows.origin_region_id` and `destination_region_id` reference different extant `regions.id` values; both owners are rechecked against current `regions.owner` before completion.
- `population_count = dependent_count + working_age_count + elderly_count` and every count is a non-negative integer.
- `pending` flows have a positive expected completion minute and zero completed minute. `completed` flows have a completion minute not earlier than authorization. Terminal rejected/redirected/cancelled rows never alter cohorts.
- Aggregate pending source reservations must not exceed the origin cohort totals; pending destination reservations must not exceed remaining incoming capacity.
- For each completed flow, origin cohort deltas equal the negative of destination cohort deltas. Domestic movement preserves the country total; international movement preserves the total across all loaded regions.
- Missing migration tables in old saves means apply the configured default without modifying legacy law rows, with no synthesized transition or flow history and zero signals.
