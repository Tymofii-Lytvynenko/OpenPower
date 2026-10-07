# Migration System Contracts

## Shared action: `ActionUpdateMigrationPolicy`

Keep the existing constructor prefix: `player_id`, `country_tag`, `migration_policy`, `border_policy`. Append optional, defaulted fields for `entry_rate`, `exit_rate`, `asylum_rate`, `family_reunification_rate`, `skilled_worker_preference`, `enforcement_strength`, and `effective_at_minute`. Omitted numeric fields retain their currently effective values; omitted effective time resolves to the current simulation minute. Reject non-finite/out-of-range values, unknown postures, unknown countries, or actors without authority to control the country. Accepted changes are persisted in `migration_policies` with a stable source and effective time.

The action is an intent only. It never edits `GameState` in the client or `src/shared`.

## Domain events

- `EventMigrationFlowCreated(flow_id, origin_region_id, destination_region_id, population_count, reason_code, at_minute)` records a newly authorized directional movement.
- `EventMigrationFlowResolved(flow_id, status, population_count, reason_code, at_minute)` records completion, cancellation, redirection, or rejection. Cohort transfer happens only with `status="completed"`.
- `EventMigrationPolicyUpdated(country_id, effective_at_minute, source, at_minute)` records an accepted effective-dated policy change.
- `EventMigrationSignalUpdated(country_id, political_pressure, service_pressure, net_flow, at_minute, law_pressure=0.0)` exposes the derived country read model to politics/economy consumers.

Events are deterministic for identical starting tables, policy, time, and ordered actions. Their durable journal serialization uses the existing `DomainGameEvent` path.

## Gameplay system: `base.migration`

**Phase**: after population, AI strategy, and diplomacy, before politics and economy. Declare explicit dependencies on `base.population`, `base.ai`, and `base.diplomacy`.

**Reads**: `countries`, `regions`, `region_adjacency`, `countries_relations`, `countries_treaties`, `countries_wars`, `treaty_effects`, `migration_policies`, `migration_policy_transitions`, `migration_flows`, `regional_infrastructure`, `domestic_production`, and `migration_signals`.

**Writes**: `regions`, `migration_policies`, `migration_policy_transitions`, `migration_flows`, and `migration_signals`. Country-level opportunity metrics are read-only inputs; the system does not duplicate them into a second population or economic ledger.

**Actions handled**: `ActionUpdateMigrationPolicy`.

**Order within an update**:

1. Normalize missing optional migration tables to registered empty schemas and seed only missing defaults.
2. Validate policy actions, schedule future transitions without replacing current policy, and apply transitions due at this minute.
3. Complete due authorized flows in stable `(expected_completion_at_minute, id)` order, capping against live source cohorts and reserved destination capacity. An already-authorized flow persists `finish_authorized`, so a later border closure does not revoke it.
4. Recompute affected country signals and only dirty/incident route candidates.
5. At the configured evaluation cadence, authorize feasible new flow records. Every no-op/rejection/redirect uses a stable reason code and zero-value flows do not mutate cohorts.

## Eligibility and effect interfaces

- Domestic routes require adjacency and same current owner, then apply the owner’s effective entry/exit policy.
- International routes require adjacency, unchanged recognized ownership, permitted relation/war status, effective origin exit and destination entry/asylum controls, and no active explicit movement sanction.
- An active explicit mobility agreement may lift a restriction only when its effect names migration/mobility access; generic treaties do not.
- Capacity policy accepts explicit region housing/employment/service overrides where present. For empty regions, all four capacities—housing, jobs, transport, and services—must be positively evidenced. Existing infrastructure access fields provide the transport/service inputs; current labor and production indicators constrain jobs.
- The pure policy returns a typed decision with direction, exact integer cohorts, reason code, deterministic score factors, and travel duration. The orchestrator is the only component allowed to apply a completed transfer.

## Downstream consumers

- `PoliticsSystem` reads unconsumed `migration_signals` once on its existing weekly evaluation boundary and applies bounded approval/stability effects plus an inspectable migration-law pressure row.
- `EconomicHealthSystem` reads unconsumed labor/service signals, bounds their effect on economic health and migration-pressure indicators, then advances the economy consumer watermark so one signal window is not applied twice.
- Existing `PopulationSystem` continues natural birth/death/aging; it reads no migration flow history and never performs migration transfers.
- The migration presenter reads the canonical policy/flow/signal/region tables and outputs country and selected-region net/gross flow, top routes, active controls, capacity pressure, and recent trend. Its panel emits only shared actions.

## Save/load, snapshots, and replay

All policy, flow, and signal state uses `BASE_TABLE_SCHEMAS`. Schema normalization supplies empty/default values for old saves. Save/load and snapshot tests assert unchanged pending status, cohort totals, and signal consumer watermarks. Replay tests submit the same ordered actions three times and compare flow rows, signals, events, and population cohorts.
