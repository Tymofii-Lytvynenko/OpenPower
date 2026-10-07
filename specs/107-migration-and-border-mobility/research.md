# Research: Migration and Border Mobility

**Status**: Complete for the initial implementation plan.

## Codebase findings

1. `GameState` is the authoritative state container; persisted state is held in registered Polars tables. `GameState.update_table` normalizes through the schema registry, and save/load, IPC snapshots, and replay already persist those tables and durable journal records.
2. `PopulationSystem` owns natural cohort changes in `regions.pop_14`, `regions.pop_15_64`, and `regions.pop_65`. There is no migration flow service or flow table today.
3. `ActionUpdateMigrationPolicy` already exists in `src/shared/actions.py` with legacy posture strings. No registered system currently consumes it. Extend it with optional, defaulted controls instead of replacing its positional contract. A separate transition table is required to retain the active policy while a future-dated change waits to become effective.
4. `region_adjacency` is loaded once through the shared region-adjacency source and is consumed by other regional route policies. `regions.owner` is the current political owner. Therefore the migration graph can reuse the authoritative adjacency and ownership tables instead of creating a parallel geographic graph.
5. `countries_relations`, `countries_treaties`, `countries_wars`, and `treaty_effects` are maintained by the diplomacy system. `treaty_effects` is a typed, explicit effect/value/detail table. Only explicit mobility-access or movement-restriction effects should alter eligibility; generic friendship or alliance must not silently open borders.
6. `InfrastructureSystem` publishes regional `transport_access`, `utilities_capacity`, `industrial_access`, `telecom_capacity`, `infrastructure`, `infrastructure_health`, `communications`, and `health_capacity`. There are no canonical housing or job-capacity fields on every legacy region. The migration capacity policy therefore needs documented, bounded proxies with optional explicit region capacity overrides, while treating missing optional fields as neutral only where the spec allows it.
7. `SystemPhase` and dependency ordering allow a migration system to run after population, AI, and diplomacy but before politics, trade, and economic health. The resulting order lets current-tick user/AI policy and diplomacy actions be applied before new flows are authorized, then lets downstream systems observe completed cohort changes.
8. `AISystem` composes deterministic `TabularAIPolicy` implementations and emits semantic actions. The migration AI must reuse this pattern and the same server-side validation and flow eligibility rules as player decisions.
9. The in-game client is built from `PanelSpec` registrations. Presenters are the read-only boundary; panels dispatch shared actions through the network client. A migration panel can expose country and selected-region summaries without mutating state.
10. `PoliticsSystem` currently performs a weekly approval/stability update and depends on population. It can consume a persisted, bounded migration signal after adding an explicit migration dependency. Economic health already publishes a migration-pressure read model; realized migration signals should be composed with—not overwrite—that output.

## Decisions

### D1. Keep region cohorts as the only population ledger

Migration flow rows describe authorization and lifecycle, not a second balance. Before completion they do not change cohorts. At completion, the system applies a capped integer cohort transfer atomically to both regions; the same counts are stored in the completed flow. A flow cannot complete if ownership, border authority, source cohorts, or capacity has changed beyond what the stored authorization permits.

### D2. Use one lifecycle for domestic and international movement

Candidate routes come from `region_adjacency`. Same-owner pairs use domestic policy; cross-owner pairs additionally require legal border eligibility from both countries, current country authority, active treaties/effects, relations, and war/sanction restrictions. A deterministic travel duration is stored at authorization time. Flow state is inspectable through `pending`, `completed`, `redirected`, `rejected`, and `cancelled` statuses and stable reason codes.

### D3. Preserve the existing action and law surface

Retain `ActionUpdateMigrationPolicy(player_id, country_tag, migration_policy, border_policy)` as the compatible constructor prefix. Append optional numeric controls and an optional requested effective minute. Persist current values in `migration_policies` and future changes in `migration_policy_transitions`; do not delete or repurpose `country_laws` or its existing migration-law presentation. The bootstrap system creates a default policy only when none exists.

### D4. Make policy effective-dated and authority-checked

The server resolves an omitted effective time to the current game minute, clamps/validates all controls, and records the effective boundary. Requests from a non-controlling actor are rejected with an inspectable result. A scheduled border closure blocks new flows at/after its boundary; an already-authorized flow uses its persisted `finish_authorized` transition rule and is not retroactively revoked by the closure.

### D5. Bound capacity with explicit overrides and existing regional read models

Optional `regions.housing_capacity`, `regions.employment_capacity`, and `regions.service_capacity` values are authoritative when present. Otherwise a pure policy function derives conservative capacity proxies from current working-age residents, regional infrastructure outputs, and country employment/labor indicators. Missing capacity evidence cannot make a zero-population destination eligible by itself: an empty region needs explicit positive housing, job, transport, and service capacity. All outputs are finite and bounded, and incoming pending flows reserve capacity so simultaneous flows cannot overbook a region.

### D6. Calculate attraction and cohorts deterministically

The pure migration policy computes a bounded route score from the existing economic, development, employment, service, access, and policy values. Integer cohort allocations are calculated from source cohort ratios and the configured skilled-worker preference, then reconciled by stable largest-remainder allocation so cohort totals exactly equal the approved count. Sort routes and flow IDs before allocation; never depend on DataFrame hash or incidental row order.

### D7. Integrate downstream effects through explicit signals

Persist country-level `migration_signals` for gross/net movement, working-age change, service pressure, and political pressure. `PoliticsSystem` consumes political pressure on its normal cadence. `EconomicHealthSystem` consumes labor/service signals alongside its existing emigration-pressure model, while the regional cohorts remain the canonical inputs for population, GDP-per-capita, and labor calculations. No client or server-layer code simulates these effects.

### D8. Persist a read model, not redundant summary state

The summary presenter derives net/gross migration, top routes, active policy, capacity, and recent trend from the policy, flow, signal, and region tables. These are already persisted and synchronized; no separate summary table is needed.

### D9. Use incremental endpoint invalidation

Cache route index, region descriptors, and candidate scores by stable table revisions plus per-region signatures. Rebuild adjacency only when its table revision changes; mark endpoints dirty when cohorts, ownership, capacity, or relevant country policy/economic indicators change. Re-evaluate only incident routes for dirty endpoints and all routes only after a genuine global condition change. Pending flow completion scans only due rows and sorts them by completion minute then ID.

### D10. Verify compatibility rather than changing the population model

Legacy saves missing migration tables normalize to empty tables/default policy rows, leave region cohorts unchanged, and do not synthesize flow history. Tests cover schema migration, `GameState` save/load and snapshots, identical three-run replay, layer boundaries, existing population tests, downstream politics/economy behavior, and the opt-in controlled 10,000-flow benchmark.

## Risks and mitigations

- **Capacity proxies vary by data quality**: prefer explicit overrides; document every fallback, use conservative bounds, and test empty-region eligibility separately.
- **Concurrent routes could overdraw source cohorts or destination capacity**: group and allocate by stable route priority before creating flows; reserve source counts and destination capacity for all pending flows.
- **Policy closure races with in-flight migration**: persist the authorization-time transition rule; new flows obey the new policy while earlier authorized flows finish deterministically.
- **Economic and political signals could be applied twice**: persist a windowed signal and a last-consumed minute; update downstream systems only on their existing cadence.
- **Scaling all pairs can exceed the benchmark**: rely on adjacency-indexed candidate routes and due-flow scans; the benchmark measures execution on the controlled local environment and reports the result rather than assuming it.
