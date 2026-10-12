# Tasks: Advanced Diplomacy & Coalition Systems

**Input**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/diplomacy-events.md`

**Tests**: Required by the requested implementation and functional acceptance criteria.

## Phase 1: Structured peace proposals

- [X] T001 [US1] Implement bounded clause normalization/validation for reparations, territory transfers, treaty annulments, and demilitarization in `modules/base/systems/world/peace_deal_policy.py`.
- [X] T002 [US1] Implement authorized proposal, multi-participant consent, expiry, final revalidation, atomic application, and peace closure in `modules/base/systems/world/advanced_diplomacy_system.py`.
- [X] T003 [P] [US1] Cover multi-clause ratification, invalid/unauthorized input, expiry, demilitarization enforcement, and same-tick AI peace closure in `tests/test_advanced_diplomacy_system.py`.
- [X] T004 [US1] Add differential tests for active, suspended, and expired AI alliance obligations plus multiple AI responders with mixed acceptance outcomes in `tests/test_advanced_diplomacy_system.py`.
- [X] T016 [US1] Add optional conciliatory/pragmatic/hawkish AI acceptance profiles with a neutral country-schema default and identical-terms differential coverage in `modules/base/schema.py`, `modules/base/systems/world/peace_deal_policy.py`, and `tests/test_advanced_diplomacy_system.py`.

## Phase 2: Expansion pressure and defensive coalitions

- [X] T005 [US2] Persist rolling expansion events/scores, form and update neighbor pacts, dissolve obsolete pacts, and publish country projections/events in `modules/base/systems/world/diplomatic_balance_system.py`.
- [X] T006 [US2] Make offensive occupation scoring symmetric for either active-war side in `modules/base/systems/world/diplomatic_balance_system.py`.
- [X] T007 [P] [US2] Cover coalition formation/dissolution and side-B occupation scoring in `tests/test_diplomatic_balance_system.py`.
- [X] T008 [US2] Exercise ActionAnnexRegion from both war orientations through `TerritorySystem` into coalition formation, including vulnerable-neighbor participation and allied-neighbor exclusion, in `tests/test_diplomatic_balance_system.py`.

## Phase 3: War exhaustion and feedback

- [X] T009 [US3] Calculate casualty, occupation, blockade, and duration contributions; update stability/force-efficiency projections and publish exhaustion events in `modules/base/systems/world/diplomatic_balance_system.py`.
- [X] T010 [P] [US3] Verify all four pressure sources, penalties, participant counts, and emitted events in `tests/test_diplomatic_balance_system.py`.
- [X] T011 [US3] Add boundary/regression tests for blockade expiry, ended-war cleanup, multiple concurrent wars, and repeated identical day events in `tests/test_diplomatic_balance_system.py`.

## Phase 4: Client feedback and final validation

- [X] T012 [P] Verify diplomatic map modes and war-panel reads for exhaustion/coalition projections in `src/client/controllers/viewport_controller.py`, `src/client/ui/panels/military/war_list_panel.py`, and their existing UI tests.
- [X] T013 Verify schema additions and peace/balance projections against migration/snapshot compatibility in `tests/test_schema_mod_migrations.py` and `tests/test_snapshot_protocol.py`.
- [X] T014 Fix and regression-test territory-ownership event publication after accepted peace cessions in `modules/base/systems/world/advanced_diplomacy_system.py` and `tests/test_advanced_diplomacy_system.py`.
- [X] T015 Run the full regression suite after the AI-obligation and bilateral-annexation cases: `684 passed, 16 skipped, 116 warnings, 190 subtests passed in 162.89s`.

## Dependencies & Execution Order

## Phase 5: Bilateral asset offers

- [X] T017 Add the schema, four shared actions, lifecycle event, system/policy registration, and player workflow in `modules/base/schema.py`, `src/shared/actions.py`, `src/shared/events.py`, `modules/base/systems/world/bilateral_trade_system.py`, `bilateral_trade_policy.py`, and `src/client/ui/panels/trade_panel.py`.
- [X] T018 Cover cash/region/research exchanges, authorization, active-war and stale-asset rejection, atomicity, counteroffers, withdrawal, expiry, and AI valuation in `tests/test_identity_bilateral_workflows.py`.
- [X] T019 Add and run the bilateral trade UI journey at 1280×720 and 800×600; recorded in `tests/ui/journeys/bilateral-trade.json` and `docs/COUNTRY_IDENTITY_AND_BILATERAL_TRADE.md`.
- [X] T020 Synchronize the trade requirements, data model, contract, implementation plan, research, and quickstart with the current single-player implementation.

- US1 proposal validation and state transitions are the foundation for same-tick settlement behavior.
- US2 and US3 consume battle/territory/treaty facts and can be tested separately, then integrated with US1 event ordering.
- T013 depends on stable table/event contracts; T015 runs after all code and tests.
- All automated tasks are complete; visual/manual acceptance gates are recorded separately in their owning feature specs.
