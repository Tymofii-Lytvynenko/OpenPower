# Feature Specification: Migration and Border Mobility

## User Scenarios & Testing

### Primary User Story

As a national leader, I want people to move between regions and countries in response to living conditions, policy, and opportunity, so that population, labour supply, development, and political pressure change as a consequence of my decisions.

### Acceptance Scenarios

1. **Create a migration flow**: **Given** two eligible regions have a border or an allowed travel route and different living conditions, **When** the demographic update runs, **Then** it creates a directional flow with a population count, origin, destination, and reason factors.
2. **Apply border policy**: **Given** a country changes its migration policy, **When** a later migration update runs, **Then** entry, exit, family reunification, and asylum flows follow the policy limits and do not bypass closed borders.
3. **Move age cohorts**: **Given** a flow contains migrants, **When** it is applied, **Then** the origin and destination population cohorts change consistently and the receiving region does not gain population without a corresponding origin or external source.
4. **Grow an empty region**: **Given** a controlled region has zero or near-zero population but has accessible housing, jobs, and transport capacity, **When** migration is permitted, **Then** it can gain population through immigration without inventing births.
5. **Change labour and development**: **Given** a large net flow arrives in a region, **When** the next economic and demographic updates run, **Then** labour supply, unemployment, GDP per capita, human development, and public-service pressure reflect the changed population.
6. **Handle political pressure**: **Given** a country receives or loses a migration flow above its configured threshold, **When** politics is evaluated, **Then** approval, stability, and relevant domestic-law pressure receive the configured effect.
7. **Use foreign policy effects**: **Given** two countries have hostile relations, an active border restriction, or an agreed mobility arrangement, **When** cross-border flow eligibility is evaluated, **Then** the applicable diplomatic or policy rule is enforced.
8. **Persist and replay**: **Given** a migration decision has been applied, **When** the game is saved, loaded, or replayed with the same ordered actions, **Then** the same flows and population changes are produced.

### Edge Cases

- A region has no connected destination, valid border, or external migration route; it cannot emit or receive an unsupported flow.
- A border closes while a flow is being processed; only the already-authorized portion completes.
- A destination reaches its housing, job, or service capacity; additional eligible migrants are redirected, delayed, or rejected according to policy.
- A migration flow would make a population cohort negative; the flow is capped by the available origin cohort.
- A country loses control of a region during the update; the flow uses the authoritative owner at the defined evaluation boundary.
- A legacy save has no migration-flow records; it starts with zero pending flows and preserves existing population totals.
- A country has no explicit migration policy; the configured default policy is used and shown to the player.
- A small numerical flow rounds to zero; it must not create a phantom demographic change or a zero-value event.

## Functional Requirements

- **FR-001**: The system MUST represent migration as a directional flow between an origin and destination, with a count, eligible population cohorts, start time, expected completion time, and status.
- **FR-002**: Flow eligibility MUST consider destination attractiveness, origin conditions, geographic or diplomatic connectivity, current policy, and available destination capacity.
- **FR-003**: The system MUST support domestic migration between regions and international migration between countries without treating either as birth, death, or manual population editing.
- **FR-004**: Migration policy MUST expose configurable controls for entry, exit, asylum, family reunification, and skilled-worker preference. A policy control MUST have an explicit effective time.
- **FR-005**: A closed or restricted border MUST prevent new ineligible flows while allowing already-authorized flows to follow the configured transition rule.
- **FR-006**: Applying a completed flow MUST subtract the moved cohort counts from the origin and add the same cohort counts to the destination. The operation MUST preserve population conservation across the affected scope.
- **FR-007**: The system MUST support working-age, dependent, and elderly migrant cohorts and MUST calculate the cohort mix deterministically from the source population and migration profile.
- **FR-008**: A region with no resident population MUST be eligible to receive immigrants when it has valid ownership, access, housing, employment, and service capacity. Immigration MUST be the only supported source of population growth for an empty region in this feature.
- **FR-009**: Migration MUST update derived labour supply, unemployment pressure, GDP-per-capita inputs, human-development pressure, and public-service load through the existing demographic and economic contracts.
- **FR-010**: Large or sustained migration flows MUST publish a domestic political signal that the politics system can use for approval, stability, and law-pressure calculations.
- **FR-011**: International flows MUST respect active border restrictions, mobility agreements, sanctions that explicitly restrict movement, and the authority of the countries controlling the origin and destination.
- **FR-012**: The system MUST expose pending, completed, redirected, rejected, and cancelled flows with their reason codes so a player can understand why a population moved or did not move.
- **FR-013**: AI-controlled countries MUST select migration policies and process flows using the same eligibility, capacity, and conservation rules as human-controlled countries.
- **FR-014**: Identical state, policy values, time, and ordered actions MUST produce identical flow amounts, cohort composition, completion times, and derived signals.
- **FR-015**: Migration state MUST survive save/load, snapshot synchronization, and replay without changing pending-flow status or population totals.
- **FR-016**: The system MUST recalculate only affected origins, destinations, borders, and policy links when no global migration condition has changed.
- **FR-017**: The feature MUST provide a readable migration summary for a selected country and region, including net migration, top origins or destinations, policy, capacity pressure, and recent trend.

## Key Entities & Data Model

- **Migration Flow**: A directional movement record linking origin, destination, cohorts, amount, cause factors, policy decision, timing, and lifecycle status.
- **Migration Policy**: A country-level policy set controlling entry, exit, asylum, family reunification, skilled-worker preference, and enforcement strength.
- **Destination Capacity**: The available housing, jobs, transport, and public-service capacity that bounds incoming migration.
- **Migration Pressure Signal**: A derived signal consumed by politics and economics to represent labour, service, and approval pressure from sustained flows.
- **Migration Summary**: A read-only aggregate of a country's and region's net flow, gross inflow, gross outflow, major routes, and unresolved capacity pressure.

## Scope Boundaries

This feature adds demographic mobility and policy effects. It does not replace the existing birth, death, ageing, fertility, life-expectancy, budget, trade, treaty, or thematic-map systems. It does not create a separate population ledger that can diverge from the authoritative region cohorts.

## Success Criteria

- **SC-001**: In conservation tests, total population across an isolated migration scenario changes only by explicitly configured external immigration and never by an unexplained flow imbalance.
- **SC-002**: 100% of ineligible border flows are rejected, redirected, or delayed with an inspectable reason code.
- **SC-003**: An empty eligible region receives population only through completed migration flows, and the receiving population equals the sum of completed incoming cohorts.
- **SC-004**: Within one demographic update after a completed flow, labour supply, unemployment pressure, GDP-per-capita input, and service load reflect the new cohorts.
- **SC-005**: Identical state and ordered actions reproduce the same migration result across three repeated runs and after save/load.
- **SC-006**: A player can identify a selected region's net migration and the active policy from the interface without inspecting raw state data.
- **SC-007**: Processing 10,000 pending flows completes within 250 milliseconds in a controlled benchmark and does not rescan unaffected region pairs.

## Assumptions & Dependencies

- **Assumption**: Existing region population cohorts remain the authoritative population source; migration changes those cohorts at the completion boundary.
- **Assumption**: Domestic and international migration use the same flow lifecycle, while international flows add border and diplomatic eligibility checks.
- **Assumption**: The initial implementation uses configurable attractiveness and capacity formulas rather than a fixed historical migration table.
- **Dependency**: Existing demographic time advancement and region population data remain available.
- **Dependency**: Existing country-law and migration-policy action contracts are extended rather than replaced.
- **Dependency**: Existing economic, politics, treaty, notification, snapshot, and save/load paths consume migration outputs.
