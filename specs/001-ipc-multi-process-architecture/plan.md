# Implementation Plan: Multi-Process IPC Architecture & Session Proxy

**Branch**: `main`  
**Feature Directory**: `specs/001-ipc-multi-process-architecture`  
**Date**: 2026-07-22  

---

## Technical Context

- **Architecture Pattern**: Multi-process producer/consumer model over `multiprocessing.Process` with 3 IPC queues (`action_queue`, `state_queue`, `progress_queue`).
- **Simulation Process Loop**: 10 TPS (100ms per tick) isolated in background daemon process (`src/server/server_process.py`).
- **Client Presentation Proxy**: 30Hz (`1.0/30.0`s) non-blocking queue polling (`src/client/client_session.py`).
- **Serialization Format**: Zero-copy Apache Arrow IPC streams (`write_ipc` / `read_ipc`) packed into byte buffers via `GameState.to_ipc()` and `GameState.from_ipc()`.
- **Command Schema**: Standardized command pattern subclasses of `GameAction` (`src/shared/actions.py`).
- **Event Bus**: Decoupled `GameEvent` signals cleared at start of each tick (`src/shared/events.py`).

---

## Constitution Check

- [x] **Principle 1 (Strict Layer Separation)**: Client (`src/client`) communicates solely via `action_queue` and Arrow IPC state snapshots. `shared` has zero logic. Server lives in background process.
- [x] **Principle 2 (Data-Oriented & Asynchronous)**: World state is stored and serialized as Polars DataFrames and PyArrow IPC streams.
- [x] **Principle 3 (Modular SOLID Design)**: Decoupled queue interface abstracts server process details from UI view controllers.
- [x] **Principle 4 (Self-Documenting Code)**: Explicit inline documentation detailing queue draining, tick timing, and process join timeouts.
- [x] **Principle 5 (Empirical Verification)**: Verified Framerate decoupling (UI @ 60+ FPS, Server @ 10 TPS) and process cleanup without zombie processes.

---

## Phase 0: Research & Technical Rationale (`research.md`)

- **Decision**: Use 3 separate multiprocessing queues (`action_queue`, `state_queue`, `progress_queue`).
- **Rationale**: Separates low-latency UI input, high-throughput binary state snapshots, and diagnostic boot initialization messages without queue contention.
- **Alternatives Considered**: Shared Memory arrays (higher complexity, risks state tearing) and REST/WebSockets (unnecessary I/O latency for single-host desktop application).

---

## Phase 1: Data Model & Contracts

### Artifacts Generated:
1. **`data-model.md`**: Outlines `GameState`, `TimeData`, `GameAction`, `GameEvent`, and Arrow IPC binary stream layout.
2. **`contracts/actions-events-ipc.md`**: Documents 10 `GameAction` schemas, 3 `GameEvent` signals, and the IPC byte packing format.
3. **`quickstart.md`**: Guide for running, verifying, and validating multi-process session isolation and process lifecycle teardown.

---

## Touch-Points & Target Files

- `src/server/server_process.py` [MODIFY]
- `src/client/client_session.py` [MODIFY]
- `src/server/session.py` [MODIFY]
- `src/server/state.py` [MODIFY]
- `src/shared/actions.py` [MODIFY]
- `src/shared/events.py` [MODIFY]
