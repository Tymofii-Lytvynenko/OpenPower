# Data Model: Covert Operations and Counterintelligence

All records are authoritative `GameState` Polars tables. The concrete table schemas in `modules/base/schema.py` remain the source of truth.

## Covert cell (`covert_cells`)

One persistent asset owned by `country_id`. `origin_country_id` and `location_country_id` distinguish recruitment from current presence; `target_country_id` and `assignment` express intended deployment. `status` tracks lifecycle (including transit, training, active, dormant, captured, retired, and lost states). `skill_level`, `training_*`, `readiness`, `concealment`, `communications_ready`, and `upkeep` determine eligibility and operation capability. `last_known_status` is presentation-safe status, not proof of current foreign information.

## Transit route (`covert_cell_routes`)

At most one current route per cell. Stores owner, endpoints, route region IDs, progress index, arrival deadline, and route status/rejection reason. Shared military movement-access rules determine whether travel remains legal. A cell in transit or blocked transit is not operational at its destination.

## Mission (`covert_missions`)

One time-bounded operation associated with one cell. Mission type is one of the eight specified profiles. Status moves through preparation, execution/resolution, and cleanup. Preparation and resolution deadlines, costs, risk, result, discovery and attribution flags, confidence, and bounded `output_json` support deterministic completion and visibility filtering.

## Intelligence finding (`covert_findings`)

A bounded, target-specific estimate with owner/audience, category, serialized value, confidence, freshness, discovery time, and expiry time. Military-force information must not contain unit identities and may be shared only under eligible treaty effects, with confidence no greater than its source estimate.

## Incident (`covert_incidents`)

An auditable consequence record scoped to explicit audience country IDs. Summary and incident type are safe for those audiences only; an undiscovered or unattributed event must not expose hidden owner or operation payload.

## Invariants

- A cell has no more than one active mission.
- Invalid actions have no cell, budget, or target side effect.
- Training advances only on completion; Elite cannot train further.
- No target receives operation details unless `discovered_by_target` is true; discovery does not imply attribution.
- Transit and domestic security coverage never imply certainty.
- Outcomes are functions of ordered authoritative state, time, action sequence, and deterministic state-derived seed.
- Empty/missing legacy covert tables are interpreted as no covert assets or findings.
