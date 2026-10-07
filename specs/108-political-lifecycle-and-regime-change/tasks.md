# Tasks: Political Lifecycle and Regime Change

**Input**: [spec.md](spec.md), [plan.md](plan.md), [data-model.md](data-model.md), [contracts/political-lifecycle.md](contracts/political-lifecycle.md)

## Phase 1: Setup and design artifacts

- [X] T001 Document the module boundaries and test gates in `specs/108-political-lifecycle-and-regime-change/plan.md`.
- [X] T002 Record existing architecture decisions and migration constraints in `specs/108-political-lifecycle-and-regime-change/research.md`.
- [X] T003 Define persistent entities and legacy defaults in `specs/108-political-lifecycle-and-regime-change/data-model.md`.
- [X] T004 Define action, event, authority, replay, and UI projection contracts in `specs/108-political-lifecycle-and-regime-change/contracts/political-lifecycle.md`.
- [X] T005 Add executable validation commands and expected outcomes to `specs/108-political-lifecycle-and-regime-change/quickstart.md`.

## Phase 2: Foundational authoritative state

- [X] T006 Add versioned party, election, law-transition, crisis, political-effect, and history tables/keys to `modules/base/schema.py` while extending `country_governments` compatibly.
- [X] T007 Add data-only law-change, election-override, and crisis-decision actions plus lifecycle outcome events to `src/shared/actions.py` and `src/shared/events.py`.
- [X] T008 Add bounded political-indicator normalization, government-form rules, deterministic fallback seeding, and legacy-normalization helpers to `modules/base/systems/politics/political_policy.py`.
- [X] T009 Add schema and legacy-save tests proving defaults preserve existing country indicators and region ownership in `tests/test_political_schema.py`.
- [X] T010 Register political lifecycle read/write contracts and deterministic system ordering in `modules/base/registration.py` and `modules/base/systems/politics/political_lifecycle_system.py`.

## Phase 3: User Story 1 - Inspect a valid government (Priority: P1)

**Goal**: Every country has a canonical, readable government state with separate bounded approval, stability, and corruption values.

**Independent Test**: Initialize a legacy world with missing lifecycle rows; every country receives one valid government state, a non-electoral form has no scheduled election, values remain bounded and separate, and region ownership is unchanged.

- [X] T011 [P] [US1] Test one-time initialization, non-electoral fallback, bounded separate values, and ownership preservation in `tests/test_political_initialization.py`.
- [X] T012 [US1] Normalize legacy government rows and initialize missing lifecycle state idempotently in `modules/base/systems/politics/political_policy.py` and `modules/base/systems/politics/political_lifecycle_system.py`.
- [X] T013 [US1] Preserve supplied party/faction rows and provide one deterministic eligible incumbent fallback with explicit ruling status in `modules/base/systems/politics/political_policy.py`.
- [X] T014 [P] [US1] Project government rules, ruling party, laws, election date, approval, stability, corruption, crisis, and recent causes in `src/client/ui/panels/politics/political_overview_presenter.py`.
- [X] T015 [US1] Add a political overview panel and register its entry using the existing client panel layout in `src/client/ui/panels/politics/political_overview_panel.py` and `src/client/ui/layouts/game_panel_registry.py`.
- [X] T016 [P] [US1] Test the overview's complete, stable, and unavailable-data projections in `tests/test_political_presenter.py`.

## Phase 4: User Story 2 - Change laws through valid transitions (Priority: P1)

**Goal**: Law changes require authority and government permission, remain pending until their effective time, and publish explicit bounded effects.

**Independent Test**: Valid actions schedule and resolve one transition; unauthorized, forbidden, unaffordable, crisis-time, cooldown, or late requests leave law state unchanged with a visible reason.

- [X] T017 [P] [US2] Test accepted/rejected authority, allowed values, cost, cooldown, crisis guard, due time, carry-over, and effect bounds in `tests/test_political_law_transitions.py`.
- [X] T018 [US2] Implement rule-driven law permissions, transition creation, deterministic due processing, and government-change carry-over/cancellation in `modules/base/systems/politics/law_transition_policy.py` and `modules/base/systems/politics/political_lifecycle_system.py`.
- [X] T019 [US2] Handle law actions, costs, journal results, cause records, and lifecycle events in `modules/base/systems/politics/political_lifecycle_system.py`.
- [X] T020 [US2] Publish effective tax, labor, migration, rights, economic, stability, and readiness signals without duplicating dependent formulas in `modules/base/systems/politics/political_effect_policy.py`, `modules/base/systems/politics/politics_system.py`, and the owning economy, migration, and readiness systems.

## Phase 5: User Story 3 - Schedule and resolve elections (Priority: P1)

**Goal**: Electoral governments resolve deterministic elections from the captured eligible party support and turnout rules; non-electoral governments do not receive elections.

**Independent Test**: Identical captured state and ordered actions produce identical turnout, results, winner, ruling authority, and next election date; an empty opposition uses its configured incumbent fallback.

- [X] T021 [P] [US3] Test interval default/override, eligible party snapshots, turnout, weighted results, deterministic tie-breaks, fallback, and next-date scheduling in `tests/test_political_elections.py`.
- [X] T022 [US3] Implement deterministic election eligibility, turnout, party vote totals, coalition/succession fallback, and outcome calculation in `modules/base/systems/politics/election_policy.py`.
- [X] T023 [US3] Schedule and resolve due elections exactly once and update the government/ruling authority atomically in `modules/base/systems/politics/political_lifecycle_system.py`.
- [X] T024 [US3] Publish election records, player-readable results, messages, and political causes in `modules/base/systems/politics/political_lifecycle_system.py` and `src/shared/events.py`.

## Phase 6: User Story 4 - Apply authorized election overrides (Priority: P2)

**Goal**: Government-configured postponement, acceleration, suspension, or succession records its authority, costs, duration, consequences, and next legal date.

**Independent Test**: Each allowed override changes only its configured schedule/consequence; invalid authority, type, duration, cost, cooldown, or crisis state is rejected without mutation.

- [X] T025 [P] [US4] Test override permissions, date bounds, costs, consequences, and rejection immutability in `tests/test_political_election_overrides.py`.
- [X] T026 [US4] Validate and apply configured election overrides through `modules/base/systems/politics/election_policy.py` and `modules/base/systems/politics/politics_system.py`.
- [X] T027 [US4] Expose legal override choices and authoritative results in `src/client/ui/panels/politics/political_overview_presenter.py` and `src/client/ui/panels/politics/political_overview_panel.py`.

## Phase 7: User Story 5 - Resolve approval and stability crises (Priority: P2)

**Goal**: Crossing configured approval/stability thresholds produces each eligible protest, strike, paralysis, or crisis once in deterministic order.

**Independent Test**: A multi-threshold jump records all applicable crises once; repeating the same update does not duplicate them; recovery closes or de-escalates according to form rules.

- [X] T028 [P] [US5] Test one-time threshold evaluation, deterministic escalation, bounded consequences, and recovery in `tests/test_political_crises.py`.
- [X] T029 [US5] Implement configured protest, strike, paralysis, and crisis triggers with incremental due-state indexes in `modules/base/systems/politics/political_crisis_policy.py`.
- [X] T030 [US5] Integrate crisis evaluation with existing stability drift and separately attributable approval/stability/corruption causes in `modules/base/systems/politics/politics_system.py`.
- [X] T031 [US5] Publish readable crisis messages/events and overview evidence in `modules/base/systems/politics/politics_system.py` and `src/client/ui/panels/politics/political_overview_presenter.py`.

## Phase 8: User Story 6 - Resolve regime transitions atomically (Priority: P2)

**Goal**: A successful coup, revolution, succession, or constitutional transition updates government, authority, laws, bounded indicators, and declared relations at one boundary; failed attempts retain the prior regime.

**Independent Test**: Success applies the entire configured outcome once; failed/detected attempts preserve the previous government and publish only configured failure consequences.

- [X] T032 [P] [US6] Test successful atomic changes, failed attempts, authority, thresholds, and unchanged territory ownership in `tests/test_political_regime_changes.py`.
- [X] T033 [US6] Implement deterministic transition preconditions, support, outcomes, and relation-effect declarations in `modules/base/systems/politics/political_crisis_policy.py`.
- [X] T034 [US6] Commit successful government/ruling-party/law/value/relation updates atomically and journal rejected attempts in `modules/base/systems/politics/political_lifecycle_system.py`.

## Phase 9: User Story 7 - Apply effects across existing domains (Priority: P2)

**Goal**: Each declared political effect reaches the owning subsystem on its next update without changing unrelated base calculations.

**Independent Test**: Controlled law changes affect only declared budget, migration, economic, rights, stability, or readiness signals within one dependent update.

- [X] T035 [P] [US7] Test effect publication, domain ownership, bounds, one-update latency, and unrelated-signal invariance in `tests/test_political_effect_integration.py`.
- [X] T036 [US7] Consume political tax/labor/economic outputs at the owning economy boundary in `modules/base/systems/economy/internal_economy_system.py` and `modules/base/systems/economy/budget_system.py`.
- [X] T037 [US7] Consume law-driven migration and readiness outputs at existing owning subsystem boundaries in `modules/base/systems/demographics/migration_system.py` and `modules/base/systems/military/readiness_system.py` (composed by `modules/base/systems/military/military_system.py`).

## Phase 10: User Story 8 - Run AI politics through shared rules (Priority: P2)

**Goal**: AI picks explainable elections, laws, and crisis actions but uses the same authority, legality, cost, deadline, and resolution path as human actions.

**Independent Test**: AI-generated action is accepted/rejected by the same authoritative handler; identical state and seed produce identical choices with an event-history reason.

- [X] T038 [P] [US8] Test AI action legality parity, deterministic choice, and human-readable choice reasons in `tests/test_political_ai.py`.
- [X] T039 [US8] Implement composable AI election/law/crisis decision policies using authoritative inputs in `modules/base/systems/world/ai/political_policy.py`.
- [X] T040 [US8] Schedule AI political intents through the shared action/journal path in `modules/base/systems/world/ai_system.py` and `modules/base/systems/politics/political_lifecycle_system.py`.

## Phase 11: User Story 9 - Persist lifecycle and inspect recent political causes (Priority: P1)

**Goal**: Save/load, snapshot sync, and replay preserve all pending dates, elections, votes, laws, crisis state, causes, and the next valid outcome; one overview exposes them readably.

**Independent Test**: Saving during each pending lifecycle state and continuing before/after load yields identical tables, events, and outcomes; overview identifies the current rules and next deadline.

- [X] T041 [P] [US9] Test snapshot IPC and legacy/current save continuation through elections, transitions, and crises in `tests/test_political_persistence.py` and `tests/test_game_state_ipc.py`.
- [X] T042 [US9] Add migration defaults/version evidence for political runtime tables in `src/server/state_migrations.py` and `tests/test_schema_mod_migrations.py`.
- [X] T043 [US9] Test deterministic 10,000-country unchanged-state processing below 500 ms in `tests/test_political_performance.py`.
- [X] T044 [US9] Run the focused political suite, save/load matrix, quickstart, and full repository suite; record measured outcomes in `specs/108-political-lifecycle-and-regime-change/quickstart.md`.
- [X] T045 [US9] Update plan assumptions and mark only empirically verified requirements/tasks complete in `specs/108-political-lifecycle-and-regime-change/plan.md` and `specs/108-political-lifecycle-and-regime-change/tasks.md`.

## Dependency order

```text
T001-T005 -> T006-T010 -> US1 (T011-T016)
US1 -> US2 (T017-T020) -> US3 (T021-T024) -> US4 (T025-T027)
US2 + US3 -> US5 (T028-T031) -> US6 (T032-T034)
US2 + US5 -> US7 (T035-T037)
US2 + US3 + US5 -> US8 (T038-T040)
US1-US8 -> US9 (T041-T045)
```

## Parallel opportunities

- Independent policy test modules within a story can be written in parallel with no production-file overlap.
- Presenter tests and core system tests can be prepared separately after the schema contract is stable.
- Cross-domain consumers are sequenced after the effect contract; economy, migration, and military ownership files are distinct.
- This run executes sequentially unless explicitly authorized to delegate.

## Implementation strategy

Complete the canonical state and government overview first, then laws and elections as independently testable increments. Add override and crisis/regime paths only after due-date and authority invariants hold. Integrate domain effects and AI through existing owners, then validate persistence, UI projection, and performance. Do not mark a requirement complete solely because a table or panel exists; require an executable scenario test and empirical result.

## Progress

- Fresh repository-wide rerun on 2026-10-07: 684 passed, 16 skipped, 116 warnings, and 190 subtests passed in 162.89 seconds; this supersedes the earlier 683-test count below.

- T025-T045 are implemented and validated. The updated political/AI/persistence/schema/IPC/layer matrix reports 71 passed in 9.73 seconds; the 10,000-country steady-state median is 0.001 seconds with unchanged table revisions. The historical full repository suite reported 524 passed, 4 opt-in performance skips, and 173 subtests passed in 151.51 seconds; the then-skipped scale gates passed separately. The latest repository-wide suite reports 683 passed, 16 skipped, 116 warnings, and 190 subtests passed in 164.78 seconds (2026-10-07). Manual interactive UI verification remains a distinct visual acceptance gate.
