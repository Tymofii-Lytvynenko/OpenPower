# Data Model: Random Event Impact and Controls

## Event definition

Static policy record owned by `random_event_policy.py`; not persisted per row.

| Field | Type | Rules |
|---|---|---|
| `type` | string | Stable catalog key; unique |
| `category` | string | One of disaster, health, economic, or configured extension category |
| `eligible_scope` | string | Region, country, or global; target must resolve before triggering |
| `conditions` | mapping | Pure eligibility predicates over existing world data |
| `probability_weight` | float | Finite and non-negative; at least one eligible enabled definition must have positive weight |
| `cooldown_days` | integer | Non-negative per event type and target |
| `severity_range` | pair of floats | Finite, `0 <= min <= max <= 1` |
| `duration_days` | integer | Positive, converted to game minutes at activation |
| `response_options` | records | Stable ID, authority, cost, availability timing, mitigation, risk, and bounded secondary effects |
| `effect_profile` | records | Domain category, subject selector, magnitude bounds, cadence, and recovery policy |

## Event instance (`random_event_instances`)

One persistent row per attempted trigger that has a resolvable target. Terminal rows remain queryable as recent/history entries.

| Field | Type | Rules |
|---|---|---|
| `id` | Utf8 (key) | Deterministic runtime ID; unique |
| `event_type`, `category` | Utf8 | Must resolve to a catalog entry or be marked `legacy_unknown` |
| `target_scope` | Utf8 | `region`, `country`, or `global` |
| `region_id` | Int32 | Existing region or zero only for non-regional scope |
| `country_id` | Utf8 | Current authorized country or empty for non-country scope |
| `seed` | UInt64-compatible integer | Captured per-trigger deterministic RNG state |
| `triggered_at_minute`, `starts_at_minute`, `expires_at_minute` | Int64 | Non-negative; start not before trigger; expiry after start |
| `severity` | Float64 | Clamped to `[0, 1]` |
| `status` | Utf8 | `active`, `resolved`, `cancelled`, `skipped`, or `disabled` |
| `response_id` | Utf8 | Empty until a response is accepted |
| `response_country_id` | Utf8 | Empty until a response is accepted |
| `effects_json` | Utf8 | Deterministic compact summary for compatibility/read-model use; typed effect rows are authoritative |
| `response_options_json` | Utf8 | Serialized, bounded choices for read-only client presentation |
| `recovery_state_json` | Utf8 | Bounded recovery progress, with `{}` as the legacy/unknown default |
| `reason` | Utf8 | Human-readable cause, skip, or terminal rationale |
| `next_update_at_minute` | Int64 | Due boundary; enables processing only lifecycle rows that need advancement |

## Event effect (`random_event_effects`)

One bounded domain effect per instance/subject/category. Uses stable ID `{event_id}:{subject_type}:{subject_id}:{category}` to make replay idempotent.

| Field | Type | Rules |
|---|---|---|
| `id` | Utf8 (key) | Stable and unique |
| `event_id` | Utf8 | Must reference an instance |
| `category` | Utf8 | Domain-owned impact category (for example infrastructure, health, labour, economy, approval, migration, or budget) |
| `subject_type`, `subject_id` | Utf8 | Explicit country, region, or global subject |
| `magnitude` | Float64 | Finite and clamped to catalog bounds |
| `unit` | Utf8 | Explicit ratio, index points, currency, or other domain-defined unit |
| `application_mode` | Utf8 | `immediate`, `recurring`, or `recoverable` |
| `starts_at_minute`, `expires_at_minute` | Int64 | Non-negative; interval is half-open |
| `last_applied_at_minute` | Int64 | Prevents duplicate recurring application |
| `status` | Utf8 | `pending`, `active`, `recovering`, `recovered`, `resolved`, `cancelled`, or `skipped` |
| `mitigation_pending` | Boolean | Set by an accepted response and cleared by the owning domain consumer after bounded mitigation is applied |
| `recovery_state_json` | Utf8 | Recovery pressure/delta not yet restored |

## Event response (`random_event_responses`)

One append-only decision record; an invalid command creates only a rejected command-result entry and never changes funds, effects, or event state.

| Field | Type | Rules |
|---|---|---|
| `id` | Utf8 (key) | Deterministic runtime ID |
| `event_id`, `response_id` | Utf8 | Must reference an active event and catalog response |
| `player_id`, `country_id` | Utf8 | Actor and authorized funding authority |
| `cost` | Float64 | Finite and non-negative; deducted only after all checks pass |
| `requested_at_minute`, `applied_at_minute` | Int64 | Non-negative; available timing must have elapsed |
| `mitigation`, `risk` | Float64 | Finite and clamped to `[0, 1]` |
| `secondary_effects_json` | Utf8 | Deterministic record of applied bounded effects |
| `status`, `reason` | Utf8 | `applied` or `rejected`, with a readable explanation |

## Event controls (`random_event_controls`)

One row per category, initialized idempotently from scenario defaults. `enabled` is explicit and category frequency is finite in the configured range. Global enablement, frequency, active cap, and scenario seed are compact scenario settings in globals. If a scenario seed is configured, its dedicated event RNG state and ID sequence are persisted in globals; otherwise event rolls compose over the campaign `DeterminismState` runtime.

## Cooldown (`random_event_cooldowns`)

One keyed row per event type and target scope/id. `cooldown_until_minute` is non-negative; a matching candidate is eligible only when the current game minute reaches this boundary. Keeping the index as a typed table avoids rescanning the full historical instance list to establish eligibility.

## State transitions

```text
eligible roll -> active -> resolved
                   |  \-> cancelled
                   | response accepted (event remains active)
                   \-> skipped when no valid target/effect scope exists
disabled after trigger -> existing instance follows its definition's finish/cancel rule
```

Legacy `active_events` list rows are imported once into `random_event_instances`, retaining known values and assigning only documented defaults; the legacy list then becomes a client read-model projection.
