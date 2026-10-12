# Implementation Plan: Multi-Process IPC Architecture & Session Proxy

**Branch**: `main`  
**Feature Directory**: `specs/001-ipc-multi-process-architecture`  
**Date**: 2026-07-22  

---

## Technical Context

- **Architecture Pattern**: Multi-process producer/consumer model over `multiprocessing.Process` with four IPC queues (`action_queue`, `state_queue`, `progress_queue`, `snapshot_ack_queue`).
- **Simulation Process Loop**: 10 TPS (100ms per tick) isolated in background daemon process (`src/server/server_process.py`).
- **Client Presentation Proxy**: `ClientSessionProxy` consumes at 30Hz from `SnapshotInbox`; its receiver thread decodes snapshots outside the render callback (`src/client/client_session.py`, `src/client/services/snapshot_inbox.py`).
- **Serialization Format**: Protocol-versioned, per-table Apache Arrow IPC buffers carried in Python multiprocessing queue packets. Protocol version 3 supports append tails for `history_snapshots` while the acknowledged prefix is unchanged and sends a changed-table replacement after compaction.
- **Command Schema**: The client wraps each `GameAction` in a sequenced `CommandEnvelope` before queue transport (`src/shared/actions.py`, `src/shared/commands.py`).
- **Event Bus**: Decoupled `GameEvent` signals cleared at start of each tick (`src/shared/events.py`).

---

## Constitution Check

- [ ] **Principle 1 (Strict Layer Separation) — OPEN**: The client communicates through action envelopes and Arrow IPC state snapshots; gameplay decisions remain in server-owned modules. However, `src/shared/state.py` and `src/shared/snapshots.py` currently perform snapshot conversion/encoding, which conflicts with Constitution 1.1's passive, standard-library-only shared layer. Resolve this placement before claiming conformance.
- [ ] **Principle 2 (Data-Oriented & Asynchronous) — OPEN**: World state uses Polars DataFrames and per-table Arrow IPC buffers. The current Python multiprocessing queues serialize packet objects and bytes, so the transport does not meet Constitution 2.1's zero-copy IPC requirement.
- [x] **Principle 3 (Modular SOLID Design)**: Decoupled queue interface abstracts server process details from UI view controllers.
- [x] **Principle 4 (Self-Documenting Code)**: Explicit inline documentation detailing queue draining, tick timing, and process join timeouts.
- [x] **Principle 5 (Empirical Verification)**: Process isolation and cleanup have automated/manual evidence. Sustained 60+ FPS is still an open acceptance gate; the latest short client observation is documented in `docs/PLAYTEST_REPORT.md` and does not pass that threshold.

---

## Phase 0: Research & Technical Rationale (`research.md`)

- **Decision**: Use four separate multiprocessing queues (`action_queue`, `state_queue`, `progress_queue`, `snapshot_ack_queue`).
- **Rationale**: Separates low-latency UI input, high-throughput binary state snapshots, snapshot acknowledgements, and diagnostic boot initialization messages without queue contention. This is the implemented transport choice; its copied queue handoff remains an open mismatch with Constitution 2.1.
- **Alternatives Considered**: Shared Memory arrays (higher complexity, risks state tearing) and REST/WebSockets (unnecessary I/O latency for single-host desktop application).

---

## Phase 1: Data Model & Contracts

### Artifacts Generated:
1. **`data-model.md`**: Outlines `GameState`, `TimeData`, `GameAction`, `GameEvent`, and Arrow IPC binary stream layout.
2. **`contracts/actions-events-ipc.md`**: Documents representative action/event contracts and the IPC packet format; the shared action and event modules remain the exhaustive source of truth.
3. **`quickstart.md`**: Guide for running, verifying, and validating multi-process session isolation and process lifecycle teardown.

---

## Touch-Points & Target Files

- `src/server/server_process.py` [MODIFY]
- `src/client/client_session.py` [MODIFY]
- `src/server/session.py` [MODIFY]
- `src/server/state.py` [MODIFY]
- `src/shared/actions.py` [MODIFY]
- `src/shared/events.py` [MODIFY]
