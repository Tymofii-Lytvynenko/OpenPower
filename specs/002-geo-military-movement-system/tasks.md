# Tasks: Geo-Coordinated Military Movement & Pathfinding

**Input**: Design documents from `/specs/002-geo-military-movement-system/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/movement.md`, `quickstart.md`

**Tests**: Tests are required by the feature success criteria and the user's implementation request.

## Phase 1: Setup

- [X] T001 Record the architecture, schema, and validation contract in `specs/002-geo-military-movement-system/plan.md`, `research.md`, `data-model.md`, `contracts/movement.md`, and `quickstart.md`.

## Phase 2: Foundational Verification

**Purpose**: Establish direct, reproducible evidence for existing math and state contracts before changing movement policy.

- [X] T002 [P] [US1] Add Haversine benchmark, date-line, and duration-clamp tests in `tests/test_military_movement_spec.py` for FR-005, SC-001, and SC-003.
- [X] T003 [P] [US1] Add recruitment-cost and weekly manpower aggregation tests in `tests/test_military_movement_spec.py` for acceptance scenarios 4–5.
- [X] T004 [P] [US1] Add rejected-order immutability, per-group independence, treaty-change waypoint, and save/load determinism tests in `tests/test_military_movement_spec.py` for FR-002, FR-003, FR-006–007, SC-004–005.
- [X] T005 [P] [US1] Add moving-fleet date-line interpolation and landing-boundary regression tests in `tests/test_naval_invasion_policy.py` for FR-008 and SC-006.
- [X] T006 [P] [US1] Add a repeatable opt-in 10,000-unit/4,561-region movement-plus-manpower benchmark in `tests/test_military_movement_performance.py` for SC-002.

## Phase 3: User Story 1 — Order and observe a legal global movement (Priority: P1)

**Goal**: Each selected unit group receives a deterministic legal route and accurate movement state; illegal orders do not mutate the unit; the client can show the intended route and action.

**Independent Test**: Run the focused movement suite from `quickstart.md`; inspect movement, readiness, route, feedback, and ownership tables after accepted, queued, rejected, treaty-changed, and invasion-boundary orders.

### Implementation

- [X] T007 [US1] Defer fortified-posture release until route and destination validation have succeeded in `modules/base/systems/military/military_system.py` so a rejected order preserves readiness per FR-003 and FR-006.
- [X] T008 [US1] Reject non-positive recruitment and missing-home-region orders before changing reserves or military count in `modules/base/systems/military/military_system.py` and record their feedback.
- [X] T009 [US1] Use the shared spherical interpolation mechanism for an in-transit fleet position in `modules/base/systems/military/naval_invasion_policy.py` so date-line proximity checks match unit movement geometry.
- [X] T010 [US1] Render accepted selected-unit route legs and intended action with affiliation-aware styling in `src/client/renderers/unit_renderer.py` and `src/client/views/game_view.py`, reusing globe projection and existing map color conventions per FR-004.
- [X] T011 [US1] Add an equivalence-preserving fast path for stationary units and vectorize ordinary movement progress updates in `modules/base/systems/military/military_system.py` without changing route-boundary or engagement behavior.
- [X] T012 [US1] Reduce weekly manpower aggregation overhead in `modules/base/systems/military/military_system.py` while preserving owner totals, null handling, and country rows.

## Phase 4: Polish & Cross-Cutting Validation

- [X] T013 [US1] Make the opt-in workload benchmark assert the SC-002 target and document runtime/hardware context in `tests/test_military_movement_performance.py` and `specs/002-geo-military-movement-system/quickstart.md`.
- [X] T014 Run all focused movement tests and the repository suite, then record actual outcomes in `specs/002-geo-military-movement-system/quickstart.md`.
- [ ] T015 Run the live-client route/color, treaty-revalidation, and invasion scenarios from `specs/002-geo-military-movement-system/quickstart.md` and record results; requires an available client window.

## Dependencies & Execution Order

- T001 is complete; T002–T006 are independent test additions.
- T007–T012 depend on the relevant failing/regression tests. T009 depends on T005; T011 and T012 depend on baseline T006 measurements.
- T013 depends on the optimizations in T011–T012. T014 depends on all code and tests. T015 is an independent human/client gate.

## Implementation Strategy

1. Add failing tests for specified math, rejected-order immutability, and current empirical performance.
2. Fix correctness issues before applying behavior-preserving optimizations.
3. Add route display only through the passive client; keep route and policy decisions authoritative in the module layer.
4. Validate each story increment, then run focused and full suites. Do not mark the performance or live-client gates complete without measured evidence.
