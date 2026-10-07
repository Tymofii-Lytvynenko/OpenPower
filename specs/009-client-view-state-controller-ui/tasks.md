---
description: "Task list for Client View State Architecture, Navigation & Audio Services"
---

# Tasks: Client View State Architecture, Navigation & Audio Services

**Input**: Design documents from `specs/009-client-view-state-controller-ui/`

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/client-runtime-ports.md`, and `quickstart.md`.

**Tests**: Tests are required by the acceptance scenarios and the user's implementation objective. Live timing/audio acceptance is recorded separately from headless evidence.

## Phase 1: Setup

**Purpose**: Record a baseline before changing the existing client services.

- [X] T001 Run the focused baseline and record exact output and third-party warnings in `specs/009-client-view-state-controller-ui/research.md` using `tests/test_client_services.py` and `tests/test_loading_view.py` (6 passed; 116 Pyglet deprecation warnings on 2026-10-07).

## Phase 2: Foundational client contracts

**Purpose**: Establish reusable tests for the task/session boundaries before story-specific lifecycle fixes.

- [X] T002 [P] Add contract and import-boundary tests for cancellable `LoadingTask`, passive `SessionPort`, and injected `SessionFactory` behavior in `tests/test_client_service_contracts.py` and `tests/test_layer_boundaries.py`.

## Phase 3: User Story 1 — Navigate, load, and operate the client (Priority: P1)

**Goal**: Complete the window-owned navigation/audio services and reliable asynchronous boot/loading flow while keeping the client passive and HUD controls composable.

**Independent Test**: Mocked tests cover all view routes, stream lifecycle, task progress/failure/cancellation, startup queue messages, resize forwarding, and passive action dispatch; the live quickstart remains a separate acceptance gate.

### Tests for User Story 1

- [X] T003 [P] [US1] Add track normalization, replacement, volume, missing-file, and backend-failure tests in `tests/test_audio_service.py`.
- [X] T004 [P] [US1] Add route construction and single-view handoff tests for all `NavigationService` destinations in `tests/test_navigation_service.py`.
- [X] T005 [P] [US1] Add loading progress, hidden-view cancellation, and late-result suppression tests in `tests/test_loading_view.py`.
- [X] T006 [P] [US1] Add new/load-session factory failure, cancellation, timeout, and child cleanup tests in `tests/test_new_game_task.py`, `tests/test_load_game_task.py`, and `tests/test_session_startup.py`.
- [X] T007 [P] [US1] Add cancellation-boundary and missing-asset behavior tests in `tests/test_editor_loading_task.py`.
- [X] T008 [P] [US1] Add 60-Hz boot scheduling, PROGRESS/READY/ERROR queue, resize forwarding, and visible progress tests in `tests/test_window_boot.py`.
- [X] T009 [P] [US1] Add HUD callback/passive-state tests and offline economy-validator coverage in `tests/test_hud_components.py`, `tests/test_client_service_contracts.py`, and `tests/test_economy_validator.py`.

### Implementation for User Story 1

- [X] T010 [US1] Harden `AudioService` track identity, stream replacement/stop cleanup, bounded volume, and recoverable diagnostics in `src/client/services/audio_service.py`.
- [X] T011 [US1] Add cooperative task cancellation and prevent hidden `LoadingView` instances from navigating after completion in `src/client/interfaces/loading.py` and `src/client/views/loading_view.py`.
- [X] T012 [US1] Use the injected session factory and guarantee new/load-session cleanup on failure or cancellation in `src/client/tasks/new_game_task.py`, `src/client/tasks/load_game_task.py`, and `src/client/views/load_game_view.py`.
- [X] T013 [US1] Add cooperative cancellation checkpoints around editor asset/map loading without moving graphics work to the worker in `src/client/tasks/editor_loading_task.py`.
- [X] T014 [US1] Inject the local session factory from `main.py`, poll boot progress non-blockingly at 60 Hz, stop polling on terminal messages, and clean up a child if proxy construction fails in `main.py` and `src/client/window.py`.
- [X] T015 [US1] Run the feature quickstart tests and record separate headless and interactive results in `specs/009-client-view-state-controller-ui/quickstart.md` and `specs/009-client-view-state-controller-ui/tasks.md`.

### Live acceptance gate

- [ ] T016 [US1] Measure one-frame view transitions and verify continuous audio, visible boot progress, rapid loading-view replacement, and resize behavior in the running desktop client; record actual results in `specs/009-client-view-state-controller-ui/quickstart.md`.

## Dependencies & Execution Order

- T001 captures the baseline before changes. T002 establishes the shared client contracts before feature tests.
- T003–T009 are independent test additions in separate files and should fail before their corresponding implementation tasks.
- T010, T011, T012, T013, and T014 touch separate production components; T012 and T013 depend on T011's cancellation contract.
- T015 depends on all automated tasks. T016 is a separate live-client gate and must not be replaced by mocks or headless tests.

## Parallel Opportunities

- T003–T009 use separate test files and can be authored/run independently before implementation.
- T010, T012, T013, and T014 can proceed independently after the shared cancellation contract in T011 is settled; T012/T013 only depend on its public task behavior.

## Implementation Strategy

Establish the baseline, prove the existing service ports, then add failing tests for user-visible lifecycle edge cases. Implement audio and task cleanup without changing the server-authoritative boundary. Validate with focused headless tests, then run the documented quickstart; leave transition/audio timing open until measured in the desktop client. Any future timing optimization requires a comparable baseline and is capped at three measured iterations.
