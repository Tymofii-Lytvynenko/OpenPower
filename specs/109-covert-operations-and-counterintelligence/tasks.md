# Tasks: Covert Operations and Counterintelligence

**Input**: Design documents from `specs/109-covert-operations-and-counterintelligence/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

## Phase 1: Setup and design validation

- [X] T001 [P] Verify the covert table/action schema against the requirements and record runtime/test context in `specs/109-covert-operations-and-counterintelligence/research.md`.

## Phase 2: User Story 1 — Operate covert cells (Priority: P1)

**Goal**: Recruit, train, assign, route, and operate a cell through the authoritative action path.

**Independent Test**: Exercise a domestic lifecycle plus a foreign transit route with resource charging and invalid-action no-side-effect checks.

- [X] T002 [P] [US1] Verify creation, capacity/funds rejection, authority, assignment, retirement, and one-active-mission invariants in `tests/test_covert_operations_system.py`.
- [X] T003 [P] [US1] Verify timed training across all skill levels, costs/upkeep, communications/readiness, and Elite cap in `tests/test_covert_operations_system.py`.
- [X] T004 [US1] Verify foreign movement-access routing and that transit/blocked cells cannot execute or contribute destination coverage in `tests/test_covert_operations_system.py`.

## Phase 3: User Story 2 — Resolve missions and counterintelligence (Priority: P1)

**Goal**: Resolve all mission profiles deterministically with bounded effects, discovery/attribution, and defensible domestic security.

**Independent Test**: Repeat the same prepared mission from identical state/seed, then compare outputs, effects, visibility, and defender outcomes.

- [X] T005 [P] [US2] Verify eight distinct mission risk/detection profiles and deterministic resolution in `tests/test_covert_operations_system.py`; inspect bounded mission-specific effects in the authoritative resolver.
- [X] T006 [P] [US2] Verify domestic-security population scaling, diminishing returns, and that transit coverage is inactive while active coverage remains non-certain in `tests/test_covert_operations_system.py`.
- [X] T007 [US2] Verify discovery versus attribution, audience-safe incidents/messages, and owner/target presentation filtering in `tests/test_covert_operations_system.py` and `tests/test_military_presenter.py`.

## Phase 4: User Story 3 — Share and inspect intelligence (Priority: P2)

**Goal**: Show authorized cell/finding information and share eligible force intelligence without increasing its source confidence.

**Independent Test**: A known owner sees confidence/freshness findings; an eligible ally receives a capped copy; an ineligible country and an undiscovered target receive none.

- [X] T008 [P] [US3] Verify espionage categories, finding expiry/freshness, force identity redaction, treaty eligibility, and source-confidence cap in `tests/test_covert_operations_system.py` and `tests/test_military_presenter.py`.
- [X] T009 [US3] Verify AI creates/trains/uses cells only through the common validated actions in `tests/test_covert_ai_policy.py`, `tests/test_ai_policies.py`, and `tests/test_ai_integration.py`.
- [X] T010 [US3] Verify snapshot/save compatibility and legacy empty covert state in `tests/test_covert_operations_system.py` and `tests/test_game_state_ipc.py`.
- [X] T011 [US3] Correct only concrete gaps exposed by T002–T010 in the existing military system, AI policy, presenter, or state schema; preserve public contracts. No uncovered correctness defect was found in the verified paths.

## Phase 5: Empirical gates and acceptance

- [X] T012 Run `tests/test_covert_operations_performance.py`, record environment and samples in `research.md`, and allow at most three measured optimization iterations if the 500 ms gate fails. If still failing after iteration three, log the problem, attempts, and outcomes and move to another specification. Gate passed; zero new tuning iterations.
- [X] T013 Run all functional commands in `quickstart.md` and record exact test outcomes in `research.md`.
- [ ] T014 Complete desktop UAT for owner/target covert overview, secrecy, and the under-30-second inspection criterion; record evidence in `research.md`. Do not substitute headless tests for this gate.

## Dependencies and execution order

- T001 precedes the acceptance work so schema and action boundaries are explicit.
- T002–T010 validate independent behaviors; T011 follows only if any check fails.
- T012 runs after behavior is stable; a passing gate requires no tuning.
- T013 is final automated verification. T014 requires an interactive desktop client and may remain open when that environment is unavailable.

## Performance policy

Feature coverage is the priority. Do not exceed three measured optimization iterations for any failing algorithm. Record each attempted change and resulting metric; if the gate still fails after iteration three, preserve the issue as deferred and continue to the next feature.
