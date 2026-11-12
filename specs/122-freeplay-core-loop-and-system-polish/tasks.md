# Tasks: Freeplay Core Loop and System Polish

**Input**: Design documents in `specs/122-freeplay-core-loop-and-system-polish/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/freeplay-start-and-playability.md`, `quickstart.md`

**Automated verification**: Every acceptance task uses pytest/session assertions or the existing `openpower ui-test` harness. No manual desktop acceptance task is included.

## Phase 1: Baseline and traceability

**Purpose**: Record the implemented systems and locate the player-loop boundary before changing gameplay behavior.

- [X] T001 Inventory the 34 registered base systems, player-facing panels, freeplay launch path, time controls, feedback, and persistence in `specs/122-freeplay-core-loop-and-system-polish/research.md`.

---

## Phase 2: User Story 1 — Start a freeplay session (Priority: P1) 🎯 MVP

**Goal**: Select a country and enter an open-ended game without requiring a campaign or scenario.

**Independent Test**: Start with a playable country and no scenario id; confirm the session reaches the game view with the selected player context and no campaign/objective row requirement.

- [ ] T002 [P] [US1] Add no-scenario launch and startup-failure cases in `tests/test_new_game_view_coverage.py` and `tests/test_freeplay_start_task.py`.
- [ ] T003 [US1] Create `src/client/ui/components/shared/freeplay_setup_window.py` from existing country and party selection components, then make it the direct default route in `src/client/views/new_game_view.py`; keep `SinglePlayerSetupWindow` for optional scenario setup.
- [ ] T004 [US1] Implement `src/client/tasks/freeplay_start_task.py` using the shared operations in `src/client/tasks/session_startup.py`; report readiness from the initial authoritative world/player context, without `ActionStartCampaign` or a `campaigns` row, and preserve cancellation cleanup.

---

## Phase 3: User Story 2 — Make decisions and see consequences (Priority: P1) 🎯 MVP

**Goal**: Use the existing time, economy, politics, military, and diplomacy systems from the player interface and understand command outcomes.

**Independent Test**: Advance/pause time, perform one valid action in each core domain, and confirm the owning authoritative state changes; reject one invalid action and confirm its reason is visible.

- [ ] T005 [P] [US2] Add deterministic session coverage for pause/speed, continued AI/world/event and scheduled demographic updates without campaign outcomes, and authoritative consequences of `ActionSetTax`, `ActionSetGovernmentForm`, `ActionMoveUnit`, and `ActionCreateTreaty` in `tests/test_freeplay_core_loop.py`.
- [ ] T006 [P] [US2] Register a freeplay UI surface and deterministic fixture/journey in `src/client/ui/testing/catalog.py`, `tests/ui/fixtures/freeplay_core_loop.json`, and `tests/ui/journeys/freeplay_core_loop.json`; assert displayed date, pause/speed action dispatch, core-panel action dispatch, report status, and artifact paths.
- [ ] T007 [US2] Trace and close any demonstrated economy or politics action gaps through `src/client/ui/layouts/game_panel_registry.py`, `src/client/ui/panels/economic_health_panel.py`, `src/client/ui/panels/politics/constitutional_form_panel.py`, `modules/base/systems/economy/economic_health_system.py`, and `modules/base/systems/politics/political_lifecycle_system.py`.
- [ ] T008 [US2] Trace and close any demonstrated military or diplomacy action gaps through `src/client/controllers/unit_interaction_controller.py`, `src/client/ui/panels/politics/treaty_editor_live.py`, `modules/base/systems/military/military_system.py`, and `modules/base/systems/world/treaty_diplomacy.py`.
- [ ] T009 [US2] Add accepted/rejected command and movement-order notice coverage, including actor filtering so AI-owned results do not appear as player errors, in `tests/test_command_feedback.py` and `tests/test_unit_order_feedback.py`; correct only proven presentation gaps in `src/client/ui/components/shared/command_feedback.py` and `src/client/ui/components/shared/unit_order_feedback.py`.

---

## Phase 4: User Story 3 — Save and resume freeplay (Priority: P1) 🎯 MVP

**Goal**: Continue the same open-ended game after loading a save, even when campaign metadata is absent.

**Independent Test**: Save and load a freeplay session with no campaign data; compare player country, date, tax policy, and a pending unit-movement order.

- [ ] T010 [P] [US3] Add freeplay save/load continuation coverage without campaign metadata in `tests/test_freeplay_save_load.py`.
- [ ] T011 [US3] Fix only persistence gaps demonstrated by T010 in `src/server/io/save_writer.py`, `src/server/io/data_load_manager.py`, or the owning session restore path; preserve legacy saves that do contain campaign data.

---

## Phase 5: User Story 4 — Keep freeplay discoverable and verifiable (Priority: P2)

**Goal**: Make the core loop easy to navigate and keep acceptance reproducible without a manual UI check.

**Independent Test**: Run the registered UI journey for direct freeplay setup, central time controls, representative gameplay panels, command feedback, and save/load affordances; assert success and the expected report/screenshot artifacts.

- [ ] T012 [US4] Use automated journey output to fix confirmed navigation/discoverability issues in `src/client/ui/layouts/game_layout.py`, `src/client/ui/layouts/game_panel_registry.py`, and `src/client/ui/components/hud/central_bar.py`; keep each panel composed through its existing owner.
- [ ] T013 [US4] Run the focused launch, core-loop, persistence, and UI journey commands from `specs/122-freeplay-core-loop-and-system-polish/quickstart.md`, then record exact commands, exit codes, and artifact paths in `specs/122-freeplay-core-loop-and-system-polish/research.md`.

---

## Dependencies and execution order

- T001 establishes the current-state inventory and is complete.
- T002 establishes launch regression cases before T003–T004 change the startup path.
- T005 and T006 can begin after T004 and run in parallel: one validates authoritative simulation state, the other validates player-facing controls and panels. T007–T009 close only gaps demonstrated by those flows.
- User Story 3 depends on a freeplay session from User Story 1. T010 establishes the persistence contract before T011 changes persistence code; it can proceed alongside User Story 2.
- User Story 4 builds on the P1 loop. T012 uses the UI journey from T006, and T013 runs/records all acceptance evidence after the implementation tasks.
- No task requires manual visual inspection or a rendered desktop approval.

## Requirement Traceability

| Requirement | Tasks |
| --- | --- |
| FR-001–FR-002 | T002–T004 |
| FR-003–FR-004, FR-006 | T005–T008, T012–T013 |
| FR-005 | T009 |
| FR-007 | T010–T011 |
| FR-008 | T004–T005 |
| FR-009 | T006, T012–T013 |
| FR-010 | T003–T009, T011–T012 |

## Success-Criterion Traceability

| Criterion | Tasks |
| --- | --- |
| SC-001 | T002–T004 |
| SC-002 | T005–T006, T013 |
| SC-003 | T005, T007–T008 |
| SC-004 | T009 |
| SC-005 | T010–T011 |
| SC-006 | T004–T005 |
| SC-007 | T006, T012–T013 |

## MVP Scope

Deliver User Stories 1–3 first: direct country-to-freeplay launch, a consequential time/action loop across the four core domains, useful rejection feedback, and save/resume without campaign data. User Story 4 closes automated UI discoverability and evidence gaps. New gameplay systems and campaign work are outside this MVP.
