# Tasks: Multi-Process IPC Architecture & Session Proxy

**Feature**: Multi-Process IPC Architecture & Session Proxy  
**Feature Path**: `specs/001-ipc-multi-process-architecture`  
**Status**: In Progress  

---

## Dependencies & Execution Strategy

```
[Phase 1: Setup] ──> [Phase 2: Foundational IPC] ──> [Phase 3: US1 Background Simulation] ──> [Phase 4: Polish]
```

- **MVP Scope**: Phase 1 through Phase 3 (decoupled multi-process process loop, Arrow IPC serialization, and action dispatch).

---

## Phase 1: Setup

Goal: Validate environment configuration, process spawn flags, and IPC dependencies.

- [ ] T001 Verify `multiprocessing.set_start_method('spawn')` and freeze support in [main.py](file:///c:/ProgramData/DEV/OpenPower/main.py)
- [ ] T002 [P] Verify PyArrow IPC streaming serialization support in [src/server/state.py](file:///c:/ProgramData/DEV/OpenPower/src/server/state.py)

---

## Phase 2: Foundational IPC Framework

Goal: Establish the 3-queue communication architecture (`action_queue`, `state_queue`, `progress_queue`).

- [ ] T003 Ensure `action_queue`, `state_queue`, and `progress_queue` instantiation in [src/client/client_session.py](file:///c:/ProgramData/DEV/OpenPower/src/client/client_session.py)
- [ ] T004 Implement zero-copy Arrow IPC serialization in `GameState.to_ipc()` and `GameState.from_ipc()` in [src/server/state.py](file:///c:/ProgramData/DEV/OpenPower/src/server/state.py)
- [ ] T005 Implement background daemon process launcher `run_server_process` in [src/server/server_process.py](file:///c:/ProgramData/DEV/OpenPower/src/server/server_process.py)

---

## Phase 3: User Story 1 — Asynchronous Background Simulation (Priority: P1)

Goal: Execute 10 TPS simulation loop in background process while client proxy polls state snapshots at 30Hz without UI frame drops.

- [ ] T006 [P] [US1] Implement `GameAction` command base class and action handlers in [src/shared/actions.py](file:///c:/ProgramData/DEV/OpenPower/src/shared/actions.py)
- [ ] T007 [P] [US1] Implement `GameEvent` signal classes (`EventNewDay`, `EventNewHour`, `EventRealSecond`) in [src/shared/events.py](file:///c:/ProgramData/DEV/OpenPower/src/shared/events.py)
- [ ] T008 [US1] Implement 10 TPS simulation loop pacing with adaptive sleep in [src/server/server_process.py](file:///c:/ProgramData/DEV/OpenPower/src/server/server_process.py)
- [ ] T009 [US1] Implement 30Hz state queue polling and queue draining in [src/client/client_session.py](file:///c:/ProgramData/DEV/OpenPower/src/client/client_session.py)
- [ ] T010 [US1] Implement background process lifecycle shutdown and join handling in `ClientSessionProxy.shutdown()` in [src/client/client_session.py](file:///c:/ProgramData/DEV/OpenPower/src/client/client_session.py)

---

## Phase 4: Polish & Performance Optimization

Goal: Verify framerate decoupling and audit zero-zombie process termination.

- [ ] T011 Audit progress queue diagnostics rendering during engine startup in [src/client/views/server_boot_view.py](file:///c:/ProgramData/DEV/OpenPower/src/client/views/server_boot_view.py)
- [ ] T012 Run quickstart validation scenario to verify 60+ FPS UI rendering decoupled from background simulation tick loop in [specs/001-ipc-multi-process-architecture/quickstart.md](file:///c:/ProgramData/DEV/OpenPower/specs/001-ipc-multi-process-architecture/quickstart.md)
