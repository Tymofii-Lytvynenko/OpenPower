# Tasks: Multi-Process IPC Architecture & Session Proxy

**Feature**: Multi-Process IPC Architecture & Session Proxy

**Feature Path**: `specs/001-ipc-multi-process-architecture`

**Status**: Implementation complete; interactive framerate acceptance remains open

---

## Dependencies & Execution Strategy

```
[Phase 1: Setup] ──> [Phase 2: Foundational IPC] ──> [Phase 3: US1 Background Simulation] ──> [Phase 4: Polish]
```

- **MVP Scope**: Phase 1 through Phase 3 (decoupled multi-process process loop, Arrow IPC serialization, and action dispatch).

---

## Phase 1: Setup

Goal: Validate environment configuration, process spawn flags, and IPC dependencies.

- [X] T001 Verify `multiprocessing.set_start_method('spawn')` and freeze support in `main.py`.
- [X] T002 [P] Verify Polars Arrow IPC table encoding/decoding through `StateSnapshotEncoder` and `StateSnapshotDecoder` in `src/shared/snapshots.py`.

---

## Phase 2: Foundational IPC Framework

Goal: Establish the 3-queue communication architecture (`action_queue`, `state_queue`, `progress_queue`).

- [X] T003 Ensure action, state, progress, and snapshot-ack queue instantiation in `src/server/launcher.py`.
- [X] T004 Implement acknowledged full/delta table-wise Arrow IPC snapshot encoding and decoding behind `GameState.to_ipc()` and `GameState.from_ipc()` in `src/shared/state.py` and `src/shared/snapshots.py`.
- [X] T005 Implement background daemon process launcher `run_server_process` in `src/server/server_process.py`.

---

## Phase 3: User Story 1 — Asynchronous Background Simulation (Priority: P1)

Goal: Execute 10 TPS simulation loop in background process while client proxy polls state snapshots at 30Hz without UI frame drops.

- [X] T006 [P] [US1] Implement the `GameAction` command base class and semantic action handlers in `src/shared/actions.py` and registered simulation systems.
- [X] T007 [P] [US1] Implement `GameEvent` signal classes and persistent domain-event journaling in `src/shared/events.py`.
- [X] T008 [US1] Implement 10 TPS fixed-step pacing with bounded catch-up and adaptive sleep in `src/server/server_process.py`.
- [X] T009 [US1] Implement 30Hz snapshot polling, queue draining, and sequence acknowledgements in `src/client/client_session.py`.
- [X] T010 [US1] Implement background process shutdown, bounded join, and terminate fallback in `ClientSessionProxy.shutdown()`.

---

## Phase 4: Polish & Performance Optimization

Goal: Verify framerate decoupling and audit zero-zombie process termination.

- [X] T011 Audit progress queue diagnostics rendering during engine startup in `src/client/views/server_boot_view.py` and the MainWindow startup flow.
- [ ] T012 Run quickstart validation scenario to verify 60+ FPS UI rendering decoupled from background simulation tick loop in [specs/001-ipc-multi-process-architecture/quickstart.md](file:///c:/ProgramData/DEV/OpenPower/specs/001-ipc-multi-process-architecture/quickstart.md) (live sample recorded at 59–60 FPS; sustained 60+ remains unverified)
