# Tasks: Multi-Process IPC Architecture & Session Proxy

**Feature**: Multi-Process IPC Architecture & Session Proxy

**Feature Path**: `specs/001-ipc-multi-process-architecture`

**Status**: Runtime implementation is in place; interactive framerate acceptance and constitutional transport/layer alignment remain open

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

Goal: Establish the four-queue communication architecture (`action_queue`, `state_queue`, `progress_queue`, `snapshot_ack_queue`).

- [X] T003 Ensure action, state, progress, and snapshot-ack queue instantiation in `src/server/launcher.py`.
- [X] T004 Implement acknowledged full/delta table-wise Arrow IPC snapshot encoding and decoding behind `GameState.to_ipc()` and `GameState.from_ipc()` in `src/shared/state.py` and `src/shared/snapshots.py`.
- [X] T005 Implement background daemon process launcher `run_server_process` in `src/server/server_process.py`.

---

## Phase 3: User Story 1 — Asynchronous Background Simulation (Priority: P1)

Goal: Execute 10 TPS simulation loop in background process while client proxy polls state snapshots at 30Hz without UI frame drops.

- [X] T006 [P] [US1] Implement the `GameAction` command base class and semantic action handlers in `src/shared/actions.py` and registered simulation systems.
- [X] T007 [P] [US1] Implement `GameEvent` signal classes and persistent domain-event journaling in `src/shared/events.py`.
- [X] T008 [US1] Implement 10 TPS fixed-step pacing with bounded catch-up and adaptive sleep in `src/server/server_process.py`.
- [X] T009 [US1] Implement 30Hz state consumption through the background `SnapshotInbox` and acknowledge decoded sequences in `src/client/services/snapshot_inbox.py` and `src/client/client_session.py`.
- [X] T010 [US1] Implement background process shutdown, bounded join, and terminate fallback in `ClientSessionProxy.shutdown()`.

---

## Phase 4: Polish & Performance Optimization

Goal: Verify framerate decoupling and audit zero-zombie process termination.

- [X] T011 Audit progress queue diagnostics rendering during engine startup in `src/client/views/server_boot_view.py` and the MainWindow startup flow.
- [ ] T012 Run quickstart validation scenario to verify sustained 60+ FPS UI rendering decoupled from background simulation tick loop in `quickstart.md`; latest short observation remains above 16.7 ms at p95, so the gate stays open.

## Phase 5: Snapshot receiver and append transport

- [X] T013 Decode snapshot packets off the render callback, preserve already published state, and support version-3 history append tails with overlap and compaction fallback in `src/client/services/snapshot_inbox.py`, `src/shared/snapshots.py`, `tests/test_snapshot_inbox.py`, and `tests/test_snapshot_protocol.py`.
- [X] T014 Drain command and snapshot-ack queues between catch-up fixed steps so pause/orders and delta acknowledgement progress are not delayed until a batch completes in `src/server/server_process.py`.

## Phase 6: Constitutional alignment

- [ ] T015 **CRITICAL** Move snapshot encoding/decoding mechanics out of `src/shared/state.py` and `src/shared/snapshots.py` into a constitution-permitted mechanism layer, leaving shared data contracts passive, per Constitution 1.1.
- [ ] T016 **CRITICAL** Resolve the mismatch between copied `multiprocessing.Queue` packet transport and Constitution 2.1's zero-copy Arrow IPC requirement: implement a conforming transport or obtain a formally approved constitutional amendment before claiming conformance.
