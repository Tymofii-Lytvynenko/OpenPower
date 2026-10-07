# Strategic Warfare Data Model

Strategic warfare is authoritative state, stored in the existing schema-registered Polars tables. Fields below describe persisted state; transient indexes and display projections are not persisted.

## Entities

### Strategic weapon (`strategic_weapons`)

One row represents an owned weapon stack/design.

| Field | Type | Meaning / validation |
| --- | --- | --- |
| `id` | string | Stable weapon/design identity; referenced by pending orders. |
| `country_id` | string | Owning country. |
| `weapon_type`, `weapon_class` | string | Scenario-facing type and ICBM/SLBM class. |
| `quantity`, `ready` | int32 | Total and launch-ready inventory; launch decrements each only after all validation succeeds. |
| `origin_region_id` | int32 | Controlled origin used for distance validation; absent/invalid origin falls back to the owner's home region. |
| `range_km` | float64 | Maximum origin-to-target distance. |
| `payload_level`, `max_payload_level` | int32 | Configured design level and design cap; launch level is additionally research-gated and limited to 1–10. |
| `operational` | bool | Destroyed or non-operational weapons cannot launch. |
| `launch_cost` | float64 | Non-negative treasury debit, committed only on accepted launch. |
| `readiness_minutes` | int32 | Scenario-configured readiness delay after manufacturing; quantity is counted when production completes, but only becomes launch-ready after this delay. |
| `flight_minutes` | int32, optional | Per-weapon strike resolution duration. Positive values override the global `strategic_flight_minutes`; zero/missing values preserve the global fallback. |
| `production_cost` | float64 | Scenario-configured per-weapon cost; non-positive values mean this row is not a production-enabled design. |
| `production_minutes` | int32 | Scenario-configured production duration; non-positive values mean this row is not a production-enabled design. |
| `required_research_level` | int32 | Minimum weapon-track level for this class/design. The strategic program has its separate configured gate. |
| `program_level` | int32 | Legacy/scenario metadata; cannot substitute for authoritative research-track gates. |
| `defense_rating` | float64 | Legacy display/stat metadata; defense resolution uses fielded `missile_defense_layers`. |

### Strategic weapon production order (`strategic_production_orders`)

A durable order identifies the producing country and configured weapon design, quantity, total paid cost, order/completion/readiness minutes, status, reason, and completion time. Only research-permitted designs with positive scenario cost and duration can be ordered. The treasury is debited when the order is accepted; manufacturing completion increases total inventory, and readiness completion increases ready inventory. If its design or research prerequisites disappear before manufacturing completes, the order is cancelled and its cost is refunded when the country still exists.

### Strategic launch order (`strategic_launch_orders`)

One row is the durable lifecycle record for a validated action. `status` progresses from `pending` to `impact`, `intercepted`, `missed`, or `cancelled`; invalid actions are rejected before a row is created. The order captures owner, weapon, resolved origin region, target identity, mode, payload yield/radius, launch and resolution minutes, authorization context, detection/attribution, serialized defense attempts, reason, and update time.

Target ownership is checked again at resolution. A changed owner or missing target cancels the order without applying impact. The weapon's inventory is consumed at accepted launch, not at impact.

### Missile-defense layer (`missile_defense_layers`)

One independently researched and fielded layer per country/installation. The row carries layer ID/type, owner, researched/operational flags, explicit region coverage and/or center/radius, maximum range, readiness, first/second attempt probabilities, and maintenance cost. Inactive, unresearched, out-of-coverage, out-of-range, or zero-readiness layers contribute no attempt. Readiness is consumed for each actual interception attempt; daily maintenance is proportional to configured coverage area.

### Strategic impact (`strategic_impacts`)

An append-only audit row references the launch order and records affected country/region, target mode, category, bounded severity, collateral flag, and minute. Intended and collateral damage are separate categories. An intercepted order records an interception impact and no downstream blast impacts.

### Research tracks (`research_tracks`)

Existing rows gate the strategic program, weapon class/payload, and defense. Weapon launch requires both `strategic_program` and `strategic_weapons` at the configured threshold. Defense requires `strategic_program` and `strategic_defense`. Asset `program_level` is not a substitute.

### Client projection

The military presenter derives owned inventory, pending-order state, payload profiles, defense coverage, and probability estimates from authoritative tables. Projection values are read-only and do not predict deterministic seeded outcomes.

## Relationships and invariants

- `strategic_launch_orders.weapon_id` identifies a weapon row; multiple pending orders for one weapon are prohibited.
- `strategic_production_orders.weapon_id` identifies an owned scenario design; production quantity is bounded by the configured maximum batch and is applied only at completion.
- `strategic_launch_orders.target_region_id` must resolve to a region owned by `target_country_id` at launch and resolution.
- `strategic_impacts.launch_order_id` references an order; all impact severity values are clamped to `[0, 1]`.
- `strategic_launch_orders.defense_result_json` captures attempt order/probability/result to make resolution auditable after save/load.
- Save/load, Arrow IPC, snapshots, and replay use the existing registered-table serialization and preserve the above records.

## Determinism

Interception and detection use the simulation seed, launch-order ID, and a stable attempt salt. No client-side randomness is used. Equal authoritative state, ordered actions, and seed produce equal persisted orders, impacts, notifications, and relation changes.
