# UN Recognition and Regional Economic Access Data Model

Authoritative state is stored in schema-registered Polars tables. Case-local roster and vote records are durable; recognition access is derived from current ownership/control, case status, and a non-withdrawn country status. No client-side copy is authoritative.

## Entities

### UN recognition case (`recognition_cases`)

One row represents one time-bounded council vote for one completed annexation claim.

| Field | Type | Meaning / validation |
| --- | --- | --- |
| `id` | string | Stable case ID derived from the annexation claim; unique per claim. |
| `annexation_claim_id` | string | Existing claim that supplies region, claimant, and former owner. |
| `region_id` | int32 | Region under the claim. |
| `claimant_id`, `former_owner_id` | string | Annexing country and former political owner. |
| `eligible_voters` | list[string] | Sorted snapshot of UN members at opening, excluding claimant and former owner. |
| `opened_at_minute`, `deadline_at_minute` | int64 | Game-time interval; deadline defaults to 30 game days after opening. |
| `status` | string | `pending`, `passed`, `rejected`, or `withdrawn`. |
| `resolved_at_minute` | int64 | Resolution or withdrawal time; zero before closure. |
| `yes_votes`, `no_votes`, `abstain_votes` | int32 | Final aggregate at resolution. |
| `reason` | string | Human-readable lifecycle result/rationale. |

### Recognition vote (`recognition_votes`)

The current decision by one eligible country on one case. The stable ID is `{case_id}:{country_id}`, so a valid replacement updates the same logical row.

| Field | Type | Meaning / validation |
| --- | --- | --- |
| `id` | string | Stable case/country key. |
| `case_id`, `country_id` | string | Existing case and captured eligible voter. |
| `vote` | string | `yes`, `no`, or `abstain`. |
| `cast_at_minute` | int64 | Submission/replacement time; must precede the deadline. |
| `source` | string | `player` or trusted `ai` source. |

### Regional recognition status (`regional_recognition_status`)

Durable bilateral position for one voter in a passed case. It also retains withdrawal history.

| Field | Type | Meaning / validation |
| --- | --- | --- |
| `id` | string | Stable `{case_id}:{country_id}` key. |
| `annexation_claim_id`, `case_id` | string | Claim and originating decision. |
| `region_id` | int32 | Recognized or unrecognized region. |
| `country_id`, `claimant_id` | string | Foreign voter and annexing country. |
| `status` | string | `recognized`, `not_recognized`, or `withdrawn`. |
| `granted_at_minute`, `withdrawn_at_minute` | int64 | Decision and reversal times. |
| `reason` | string | Decision/withdrawal context. |

### Explicit regional production (`regional_production`)

Optional scenario data declares a subset of national resource production at an exact region. Fields are stable row ID, country, region, resource ID, and non-negative finite `domestic_production`. A region must resolve uniquely and the sum for a country/resource cannot exceed its national market production. Missing regional records remain unattributed; they are never synthesized from national totals.

## Relationships and Invariants

- At most one recognition case is created for an annexation claim, including after repeated ticks or save/load.
- Votes must reference a case and a country in its captured voter roster; only one current vote per pair is used for resolution.
- A case passes only if `yes_votes > len(eligible_voters) / 2` at or after its deadline.
- A passed case records `recognized` for yes voters and `not_recognized` for all other captured voters. A rejected case grants no recognition.
- A claimant has domestic access only while it owns and controls the region. Foreign access requires a passed case and a current recognized status.
- Owner/controller reversal withdraws the case and recognized statuses; it does not mutate territory, occupation, or military ownership.
- Explicit bilateral trade rows retain `source_region_id`; only source-tagged allocations are recognition-gated. National-only flows have no inferred region.
- Existing schema registration and serialization carry all persisted records through saves, snapshots, and IPC.

## Determinism

Case and voter iteration is sorted by stable IDs. AI policy derives its decision from the same diplomatic facts and fixed thresholds, without random sampling. Given identical authoritative state, time, and ordered actions, the resulting votes, statuses, events, and regional-access decisions are identical.
