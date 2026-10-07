# Specification Quality Checklist: Migration and Border Mobility

**Purpose**: Validate specification completeness and quality before planning
**Created**: 2026-08-23
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Reviewed against the existing demographic, economy, diplomacy, persistence, and client-authority boundaries.

## Implementation and acceptance evidence

Reviewed 2026-10-06 against the current implementation and automated tests. This section records implementation coverage; it does not replace an interactive visual acceptance run.

| Requirement | Implementation | Automated evidence |
|---|---|---|
| FR-001 | `modules/base/systems/demographics/migration_system.py`; `migration_flows` schema | `test_migration_system.py::test_month_boundary_creates_only_nonzero_supported_flow` |
| FR-002 | `migration_policy.py`: route index, border access, attraction, destination capacity | `test_migration_policy.py` route, border, capacity, and cohort cases |
| FR-003 | Shared domestic/international lifecycle in `MigrationSystem` | `test_month_boundary_creates_only_nonzero_supported_flow`; `test_completed_cohorts_reach_labor_gdp_per_capita_and_service_pressure` |
| FR-004 | Effective-dated country controls and persisted transitions | `test_migration_system.py::test_future_policy_transition_preserves_current_policy_and_authorized_flow`; policy validation tests |
| FR-005 | Authorized-flow transition rule plus current border checks for restricted transitions | `test_future_policy_transition_preserves_current_policy_and_authorized_flow`; `test_closed_border_rejects_new_international_flow` |
| FR-006 | Exact cohort subtraction/addition and ordered reservation handling | `test_future_policy_transition_preserves_current_policy_and_authorized_flow`; `test_due_flows_resolve_in_order_without_overdrawing_source_or_capacity` |
| FR-007 | Deterministic integer cohort allocation | `test_migration_policy.py::test_migrant_cohorts_are_integer_conserved_and_deterministic` |
| FR-008 | Empty-region access requires explicit capacity, access, and ownership; completed arrivals are the only population addition in this lifecycle | `test_empty_destination_requires_positive_explicit_capacity_and_access`; empty-destination completion in `test_future_policy_transition_preserves_current_policy_and_authorized_flow` |
| FR-009 | Existing population, economic-health, economy, and infrastructure projections consume authoritative cohorts | `test_completed_cohorts_reach_labor_gdp_per_capita_and_service_pressure`; `test_migration_cohorts_reweight_existing_country_service_projection` |
| FR-010 | Windowed flow signals are consumed once by politics and economic health | `test_politics_consumes_migration_pressure_once_and_records_law_review_signal`; `test_daily_profile_consumes_migration_service_pressure_once` |
| FR-011 | Current ownership, border policy, relations, war, treaty, and movement-sanction validation | `test_active_war_and_explicit_movement_sanction_are_hard_blocks`; `test_hostile_relation_blocks_mobility_unless_explicit_access_agreement_exists`; ownership/cancellation lifecycle cases |
| FR-012 | Pending/completed/redirected/rejected/cancelled rows, reason codes, durable events, and presenter labels | `test_capacity_change_redirects_authorized_flow_to_accessible_neighbor`; `test_country_summary_exposes_redirected_capacity_outcome`; other migration lifecycle and presenter tests |
| FR-013 | AI policy emits the same semantic policy action and uses the authoritative server path | Both tests in `test_migration_ai_policy.py`; global AI treaty-contract test in `test_ai_policies.py` |
| FR-014 | Stable flow IDs, cohort allocation, event order, and signal materialization | `test_three_identical_ordered_runs_replay_the_same_migration_trace` |
| FR-015 | Generic save/load and snapshot state carry pending flows, cohorts, and consumer watermarks | `test_pending_flow_and_signal_watermarks_survive_snapshot_and_save_load` |
| FR-016 | Cached adjacency plus changed-region/country signatures limit route reevaluation to affected endpoints | `MigrationSystem._get_route_index`, `_dirty_region_ids`, `_incident_pairs`; `test_due_flow_processing_scales_with_due_rows_in_large_pending_table` |
| FR-017 | Immutable country/region summaries expose net flow, policy, routes, capacity pressure, and reasons | `test_country_summary_exposes_policy_current_window_routes_and_reasons_without_mutation`; `test_region_summary_includes_capacity_pressure_pending_flow_and_reason` |

| Success criterion | Evidence and status |
|---|---|
| SC-001 | Automated conservation across completion, reroute, and reservation cases; focused suite passed. |
| SC-002 | Border/war/sanction/policy/capacity rejections and redirects carry inspectable reasons; focused suite passed. |
| SC-003 | An eligible empty destination receives exactly the authorized cohorts; completion test above. |
| SC-004 | Labor, GDP-per-capita inputs, service load, and economic pressure are asserted after completion; focused suite passed. |
| SC-005 | Three identical ordered replays plus snapshot/save-load round-trip tests passed. |
| SC-006 | Presenter values and panel registration/construction are covered headlessly. **Interactive visual confirmation in a running client remains pending**; no claim is made that a manual UI session was performed. |
| SC-007 | Controlled benchmark: 10,000 pending flows, 100 due, `0.075s`, `1 passed` (gate target `<250ms`). |

Implementation note: this workspace's region input contains duplicate region IDs. Infrastructure projection now deduplicates only the derived projection key before joining, preserving original region rows and preventing repeated refreshes from multiplying records; `test_duplicate_region_ids_do_not_multiply_on_repeated_projection_refreshes` covers this compatibility case.
