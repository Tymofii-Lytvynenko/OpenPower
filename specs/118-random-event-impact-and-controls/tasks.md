# Tasks: Random Event Impact and Controls

**Input**: Design documents from `specs/118-random-event-impact-and-controls/`

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/random-events.md`, `quickstart.md`

**Tests**: Requested by the user and required by the feature; tests are included before implementation where they define behavior.

**Organization**: One end-to-end user story, delivered in testable increments matching the acceptance scenarios.

## Phase 1: Setup

**Purpose**: Establish the reusable event catalog and typed persistence surfaces.

- [X] T001 [P] Define immutable event definitions, bounds, response profiles, and default controls in `modules/base/systems/world/random_event_policy.py`
- [X] T002 [P] Add typed instance, effect, response, category-control, and per-target cooldown schemas and keys in `modules/base/schema.py`

---

## Phase 2: Foundational

**Purpose**: Define action/event contracts and preserve legacy state before completing user-visible behavior.

- [X] T003 Add scenario-control and response action dataclasses in `src/shared/actions.py`
- [X] T004 Add backward-compatible lifecycle domain events in `src/shared/events.py`
- [X] T005 Declare table reads/writes and action handlers for the random-event system in `modules/base/systems/world/random_events_system.py`
- [X] T006 Add contract tests for catalog bounds, table schema types, action routing, and backward-compatible event construction in `tests/test_random_event_contracts.py`

---

## Phase 3: User Story 1 — Bounded, inspectable, controllable events

**Story goal**: Players and scenario administrators can trigger, inspect, control, and respond to deterministic world events whose effects flow through existing domain systems.

**Independent test criteria**: A seeded simulation creates one eligible event with a stable target/seed/lifecycle; disabled or cooling-down categories do not trigger; accepted responses spend once and mitigate; invalid responses spend nothing; downstream changes remain bounded; history and state survive a save/snapshot round-trip.

- [X] T007 [P] Test catalog validation, severity clamping, and bounded effect materialization in `tests/test_random_event_policy.py`
- [X] T008 Test lifecycle transitions, due-boundary processing, cooldowns, active caps, category/global disable, and legacy import in `tests/test_random_events_system.py`
- [X] T009 Implement category controls, deterministic eligibility, cooldown tracking, stable target selection, instance creation, and lifecycle history in `modules/base/systems/world/random_events_system.py`
- [X] T010 Test that accepted responses deduct cost once and invalid, unauthorized, unavailable, duplicate, or underfunded responses cause no partial mutation in `tests/test_random_event_responses.py`
- [X] T011 Implement atomic response authorization, cost, mitigation, risk, and secondary-effect recording in `modules/base/systems/world/random_events_system.py`
- [X] T012 Test bounded disaster damage and idempotent event-source handling in `tests/test_random_event_effects.py`
- [X] T013 Extend the existing infrastructure effect consumer to use typed effect records and explicit category stacking bounds in `modules/base/systems/world/infrastructure_system.py`
- [X] T014 Implement health-crisis effects through existing population, migration, labour, public-service, and politics contracts in `modules/base/systems/demographics/population_system.py`, `modules/base/systems/demographics/migration_system.py`, `modules/base/systems/economy/economic_health_system.py`, and `modules/base/systems/politics/politics_system.py`
- [X] T015 Implement boom/strike and budget effects through existing economy, resource, labour, and budget contracts in `modules/base/systems/economy/internal_economy_system.py`, `modules/base/systems/economy/economic_health_system.py`, and `modules/base/systems/economy/budget_system.py`
- [X] T016 Add scenario/global control and valid/invalid response integration tests in `tests/test_random_event_controls_integration.py`
- [X] T017 Add a readable event-history presenter projection with location, effects, response, expiry, and recovery details in `src/client/ui/panels/service/event_feed_presenter.py`
- [X] T018 Add player-facing category/global controls and response choices through the existing service/event UI, dispatching shared actions only in `src/client/ui/panels/service/`
- [X] T019 Test deterministic save/load, snapshot synchronization, and legacy active-event migration in `tests/test_random_event_persistence.py`
- [X] T020 Implement authoritative-table/legacy-projection synchronization and legacy event migration in `modules/base/systems/world/random_events_system.py`
- [X] T021 Add a due-record benchmark for 10,000 active instances and 100,000 effect records in `tests/test_random_event_performance.py`
- [X] T022 Optimize lifecycle processing to visit only due rolls, instances, effects, and recovery timers when settings are unchanged in `modules/base/systems/world/random_events_system.py`
- [X] T023 Validate downstream requirements and full focused regressions in `tests/test_random_event_acceptance.py`

---

## Final Phase: Polish & Cross-Cutting Concerns

- [X] T024 Run the complete focused validation matrix from `specs/118-random-event-impact-and-controls/quickstart.md` and record measured evidence in that file
- [X] T025 Run the repository suite and resolve only failures attributable to this feature without suppressing unrelated failures in `specs/118-random-event-impact-and-controls/quickstart.md`

## Dependencies

```text
T001 + T002 -> T003 + T004 -> T005 + T006
T007 -> T009; T008 -> T009
T010 -> T011
T012 -> T013
T009 + T011 -> T014 + T015 -> T017 + T018
T009 + T011 + T013 + T014 + T015 -> T019 + T020 -> T021 + T022 -> T023 -> T024 -> T025
```

## Parallel Opportunities

- T001 and T002 are independent files.
- After the contracts are agreed, T007/T008/T010/T012 can be authored independently; implementation tasks touching the same system must remain sequential.
- T014 and T015 affect distinct existing domain systems, but should only begin after T009/T011 define the stable effect contract.
- T017 can proceed after the instance/effect read model is stable; T018 depends on the action contracts and presenter.

## Parallel Example: User Story 1

```text
Task: T007 Catalog/eligibility tests in tests/test_random_event_policy.py
Task: T010 Atomic response tests in tests/test_random_event_responses.py
Task: T012 Infrastructure-bound/idempotency tests in tests/test_random_event_effects.py
```

## Implementation Strategy

### MVP First

Complete setup/foundational work, deterministic event lifecycle, category/global controls, atomic responses, and legacy migration; independently validate seeded triggering and command rejection before adding every downstream effect and UI path.

### Incremental Delivery

1. Establish typed contracts and persistent event rows.
2. Deliver deterministic eligibility, control, response, and history behavior.
3. Integrate bounded effects through the existing infrastructure, health, migration, economy, budget, and politics domains.
4. Surface event details and responses in the client.
5. Verify persistence, compatibility, and the 10k/100k due-record benchmark.

## Progress

- T001–T025 are implemented and validated; the expanded focused matrix reports 150 passed in 10.66 seconds. The historical repository suite reported 524 passed, 4 opt-in performance skips, and 173 subtests passed in 151.51 seconds; the then-skipped scale benchmarks and the slow real-session save/load round-trip passed. Latest repository-wide suite: 684 passed, 16 skipped, 116 warnings, and 190 subtests passed in 162.89 seconds (2026-10-07). T026 remains open pending the human-visible event-feed/control workflow.

## Phase 4: Convergence

- [ ] T026 [US1] Perform the human-visible event-feed and control workflow; record the 30-second inspection outcome, response authorization/cost behavior, category disable boundary, and recovery visibility in `quickstart.md` per SC-006 and US1/AC7 (partial, MEDIUM).
