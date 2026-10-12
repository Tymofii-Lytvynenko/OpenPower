# Feature Specification: Multi-Process IPC Architecture & Session Proxy

## User Scenarios & Testing

### Primary User Story
As a grand strategy player, I want the game simulation to execute in a separate background process (`run_server_process`) from the graphical user interface (`ClientSessionProxy`), so that complex global simulation processing (at 10 TPS) never causes frame rate drops, UI freezing, or input lag in the rendering loop (at 60+ FPS).

### Acceptance Scenarios
1. **Background Simulation Execution**: **Given** a started game session, **When** the simulation ticks, **Then** state processing occurs asynchronously in the server process (`multiprocessing.Process`, daemon mode) at a target 10 TPS without blocking UI frame rendering.
2. **Acknowledged Arrow IPC State Sync**: **Given** updated simulation state at the end of a tick, **When** the server transmits a full snapshot or an acknowledged table delta through `state_queue`, **Then** a background receiver decodes it, the client consumes the latest complete state on its normal update, and the receiver acknowledges each successfully decoded sequence.
3. **Player Action Dispatch**: **Given** a player issuing commands, **When** the client submits a `GameAction` subclass (`ActionSetTax`, `ActionBuildUnit`, `ActionMoveUnit`, etc.), **Then** `ClientSessionProxy.receive_action` wraps it in a sequenced `CommandEnvelope` and pushes that envelope to `action_queue` for server tick ingestion.
4. **Graceful Process Shutdown**: **Given** window closure or menu exit, **When** `shutdown()` executes, **Then** `"SHUTDOWN"` is posted to `action_queue`, allowing 2.0 seconds for clean join before resorting to `process.terminate()`.
5. **Catch-up Control Responsiveness**: **Given** the server has several fixed steps to catch up, **When** queued commands or snapshot acknowledgements are available before a pending step, **Then** it drains those queues between consecutive steps and encodes each completed step before advancing to the next.

### Edge Cases
- State queue backpressure during heavy UI lag: the bounded state queue may drop a just-encoded packet, while the snapshot encoder keeps deltas cumulative from the last acknowledged sequence; the background receiver decodes packets in sequence and the renderer consumes only a complete published state.
- Snapshot decoding fails or the protocol version is unsupported: keep the most recently published client state, report the protocol error, and do not acknowledge the invalid packet.
- Special editor commands: `"SAVE_MAP_CHANGES"` string command bypasses standard game action queue and triggers direct disk export.
- Server startup exceptions: Startup errors are caught and piped as `("ERROR", 0.0, str(e))` tuples across `progress_queue` to inform the loading view.

## Functional Requirements

- **FR-001**: Multi-Core Isolation: `run_server_process` MUST run in a dedicated `multiprocessing.Process` with zero direct memory sharing or OpenGL context inheritance.
- **FR-002**: Inter-Process Communication MUST use multiprocessing queues for `action_queue` (UI-to-server commands), `state_queue` (server-to-UI snapshots), `progress_queue` (startup progress/errors), and `snapshot_ack_queue` (client acknowledgements for delta bases).
- **FR-003**: 10 TPS Paced Simulation Loop: Server process MUST pace tick execution at 10 TPS (100ms per tick) using `time.perf_counter()` and adaptive `time.sleep()`.
- **FR-004**: 30Hz Client State Polling: Client proxy MUST poll for a completed state at 30Hz with accumulator throttling to preserve UI thread performance.
- **FR-005**: Off-Thread Snapshot Decode: Full/delta packet decoding and table reconstruction MUST run outside the render callback; the client update MUST consume only fully decoded snapshots, and decoding a later delta MUST NOT mutate a state object already published to UI consumers.
- **FR-006**: Versioned Append Deltas: Snapshot packets MUST declare a protocol version. Protocol version 3 MAY carry append-only tails for `history_snapshots` when the acknowledged prefix is unchanged; when compaction rewrites that prefix, the sender MUST transmit a full changed-table payload. The decoder MUST handle overlapping tails without duplicate rows and reject unsupported versions.
- **FR-007**: Catch-up Queue Draining: During a bounded catch-up batch, the server MUST drain command and snapshot-ack queues between fixed steps so pause/orders and acknowledgement progress are not deferred until the batch ends.

## Key Data Contracts & Schemas

World tables are encoded individually as Arrow IPC payloads. The server sends a full initial snapshot and then table deltas against the most recently acknowledged snapshot sequence; this avoids promising zero-copy semantics across Python serialization and multiprocessing queues.

The following action types are representative, not exhaustive; feature-specific action contracts are defined by their owning specifications.

### Representative Actions (`src/shared/actions.py`)
- `GameAction(player_id: str)`: Base class.
- `ActionSetRegionOwner(region_id: int, new_owner_tag: str)`
- `ActionSetTax(country_tag: str, new_tax_rate: float)`
- `ActionSetGameSpeed(speed_level: int)` (Levels 1: 48s/day, 2: 24s/day, 3: 12s/day, 4: 2.4s/day, 5: 0.6s/day)
- `ActionSetPaused(is_paused: bool)`
- `ActionSaveGame(save_name: str)`
- `ActionBuildUnit(country_tag: str, unit_type: str, count: int)`
- `ActionMoveUnit(unit_id: str, target_region_id: int, target_latitude: float, target_longitude: float)`
- `ActionUpdateBudget(country_tag: str, allocations: dict)`

### Core Time Signals (`src/shared/events.py`)
- `GameEvent`: Base class.
- `EventNewDay(day: int, month: int, year: int)`: Fired at 00:00.
- `EventNewHour(hour: int, total_minutes: int)`: Fired every in-game hour.
- `EventRealSecond(game_seconds_passed: float, is_paused: bool)`: Fired at 1Hz real time.

Other transient and persistent domain events are defined by their owning feature specifications; `src/shared/events.py` is the exhaustive implementation list.

## Success Criteria

- **SC-001**: Framerate Decoupling: UI rendering stays at 60+ FPS while server process runs heavy simulation at 10 TPS.
- **SC-002**: Bounded Snapshot Cost: a full snapshot of 2,000 tactical rows serializes and round-trips in under 1.5 seconds with a payload below 2 MB, and headless decoding/presentation for 100 engagement summaries stays below 100 ms.
- **SC-003**: Reliable Lifecycle: 100% of session shutdowns terminate background processes without leaving zombie Python processes.

## Assumptions & Dependencies

- **Assumption**: Polars Arrow IPC payloads preserve table schemas and values across process transfer; snapshot sequence acknowledgements keep incremental deltas reconstructible.
- **Assumption**: Arrow IPC buffers are serialized through Python multiprocessing queues; the queue transport is not zero-copy.
- **Dependency**: Python `multiprocessing` library handles process spawning.
