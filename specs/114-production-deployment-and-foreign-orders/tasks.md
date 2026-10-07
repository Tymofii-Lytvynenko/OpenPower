# Tasks: Production, Deployment, and Foreign Orders

**Input**: Design documents from `specs/114-production-deployment-and-foreign-orders/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

## Phase 1: Setup

- [x] T001 [P] Record runtime, Polars thread count, queue/transit workload shape, and baseline result in `specs/114-production-deployment-and-foreign-orders/research.md`.

## Phase 2: User Story 1 — Queue and deliver domestic production (Priority: P1)

**Goal**: Allocate national capacity predictably and place completed groups into valid deployment transit.

**Independent Test**: Queue competing orders, change priority/pause state, complete and split one order, and verify route/domain and exactly-once arrival invariants.

- [x] T002 [P] [US1] Verify configured output × health × coefficient and priority/partial allocation in `tests/test_production_capacity_policy.py`.
- [x] T003 [P] [US1] Verify queue funding, pause/resume, reprioritization, cancellation, and retained partial work in `tests/test_research_program_system.py`.
- [x] T004 [US1] Verify completion provenance, deployment queue, group splitting, valid domain destinations, transit availability, route blocks, and arrival readiness in `tests/test_research_program_system.py` and `tests/test_military_movement_spec.py`.
- [x] T005 [US1] Verify player-visible capacity, progress, ETA, funding, destination, and blocking reasons in `src/client/ui/panels/military/unit_production_panel.py` and `src/client/ui/panels/military/presenter.py`.

## Phase 3: User Story 2 — Buy foreign and used forces (Priority: P1)

**Goal**: Use seller-approved contracts and eligible existing inventory through a single payment/ownership/transit pipeline.

**Independent Test**: Exercise a valid new order and used listing transfer, then reject unauthorized, embargoed, duplicate, underfunded, and no-acceptance cases without side effects.

- [x] T006 [P] [US2] Verify buyer/seller authority, treaty/scenario permission, standing and per-order acceptance, and seller-owned design eligibility in `tests/test_foreign_order_system.py`.
- [x] T007 [P] [US2] Verify 125% default contract pricing, delivery payment/ownership timing, cancellation incurred costs and relation penalty, and one-unit creation in `tests/test_foreign_order_system.py`.
- [x] T008 [US2] Verify 75% used-unit price, listing withdrawal, embargo exclusion, stack splitting, duplicate purchase rejection, and shared route/readiness state in `tests/test_foreign_order_system.py` and `tests/test_military_market_presenter.py`.
- [x] T009 [US2] Verify only eligible countries can inspect foreign designs and that seller acceptance state/order costs/statuses are visible in `tests/test_military_market_presenter.py` and production UI tests.

## Phase 4: User Story 3 — Continue production and transfers safely (Priority: P2)

**Goal**: Preserve partial work, routes, payments, ownership, and AI behavior across deterministic continuation and save boundaries.

**Independent Test**: Continue a partial production order and an in-transit new/used unit from snapshot and disk save; compare state and next transition.

- [x] T010 [P] [US3] Verify AI production and market choices submit through the shared authoritative actions in `tests/test_ai_policies.py` and `tests/test_ai_integration.py`.
- [x] T011 [US3] Verify production, deployment, route, contract, payment, and listing state across snapshot/save/load and deterministic continuation in feature persistence tests.
- [x] T012 [US3] Fix only concrete functional gaps exposed by T002–T011 in the existing production, movement, foreign-order, schema, or presenter systems.

## Phase 5: Empirical gates and final acceptance

- [x] T013 Run `tests/test_production_deployment_performance.py` with 50,000 orders and 100,000 transit records; record environment and samples in `research.md`. If the 1-second gate fails, allow at most three measured optimization iterations. If it still fails after iteration three, record every attempt/outcome and defer the issue before moving to another specification.
- [x] T014 Run all functional commands in `quickstart.md` and record exact test outcomes in `research.md`.
- [ ] T015 Complete interactive UAT for determining completion time and arrival location within 30 seconds; record evidence in `research.md`. Do not treat headless tests as a UI pass.

## Dependencies and execution order

- T001 precedes measurements. T002–T011 are independent acceptance groups; T012 follows only where a gap is demonstrated.
- T013 follows functional stabilization. Stop optimization when a gate passes; never exceed three measured iterations on a failing algorithm.
- T014 is the final automated regression. T015 requires an available desktop client.

## Performance policy

Implementation coverage takes priority over extended tuning. For each failing algorithm, record baseline and every attempted optimization with its measured result; after attempt three, document any remaining performance problem as deferred and continue to the next specification.
