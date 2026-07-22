# Feature Specification: Multi-Process IPC Architecture & Session Proxy

## User Scenarios & Testing

### Primary User Story
As a grand strategy player, I want the game simulation to execute in a separate background process (`run_server_process`) from the graphical user interface (`ClientSessionProxy`), so that complex global simulation processing (at 10 TPS) never causes frame rate drops, UI freezing, or input lag in the rendering loop (at 60+ FPS).

### Acceptance Scenarios
1. **Background Simulation Execution**: **Given** a started game session, **When** the simulation ticks, **Then** state processing occurs asynchronously in the server process (`multiprocessing.Process`, daemon mode) at a target 10 TPS without blocking UI frame rendering.
2. **Zero-Copy State Sync**: **Given** updated simulation state at the end of a tick, **When** the server transmits state snapshots via Apache Arrow IPC (`state.to_ipc()`), **Then** the client process polls the `state_queue` at 30Hz (`1.0/30.0`s interval) and reconstructs state (`GameState.from_ipc()`).
3. **Player Action Dispatch**: **Given** a player issuing commands, **When** the client submits a `GameAction` subclass (`ActionSetTax`, `ActionBuildUnit`, `ActionMoveUnit`, etc.), **Then** `ClientSessionProxy.receive_action` pushes the object to `action_queue` for server tick ingestion.
4. **Graceful Process Shutdown**: **Given** window closure or menu exit, **When** `shutdown()` executes, **Then** `"SHUTDOWN"` is posted to `action_queue`, allowing 2.0 seconds for clean join before resorting to `process.terminate()`.

### Edge Cases
- State queue flooding during heavy UI lag: Server drains unread old frames from `state_queue` before pushing `latest_ipc` to ensure client always receives the newest frame.
- Special editor commands: `"SAVE_MAP_CHANGES"` string command bypasses standard game action queue and triggers direct disk export.
- Server startup exceptions: Startup errors are caught and piped as `("ERROR", 0.0, str(e))` tuples across `progress_queue` to inform the loading view.

## Functional Requirements

- **FR-001**: Multi-Core Isolation: `run_server_process` MUST run in a dedicated `multiprocessing.Process` with zero direct memory sharing or OpenGL context inheritance.
- **FR-002**: Three-Queue Inter-Process Communication: Communication MUST occur over 3 distinct multiprocessing queues: `action_queue` (UI->Server actions), `state_queue` (Server->UI state snapshots), and `progress_queue` (Server->UI initialization progress).
- **FR-003**: 10 TPS Paced Simulation Loop: Server process MUST pace tick execution at 10 TPS (100ms per tick) using `time.perf_counter()` and adaptive `time.sleep()`.
- **FR-004**: 30Hz Client State Polling: Client proxy MUST poll `state_queue` at 30Hz with accumulator throttling to preserve UI thread performance.

## Key Data Contracts & Schemas

### Actions Schema (`src/shared/actions.py`)
- `GameAction(player_id: str)`: Base class.
- `ActionSetRegionOwner(region_id: int, new_owner_tag: str)`
- `ActionSetTax(country_tag: str, new_tax_rate: float)`
- `ActionSetGameSpeed(speed_level: int)` (Levels 1: 48s/day, 2: 24s/day, 3: 12s/day, 4: 2.4s/day, 5: 0.6s/day)
- `ActionSetPaused(is_paused: bool)`
- `ActionSaveGame(save_name: str)`
- `ActionBuildUnit(country_tag: str, unit_type: str, count: int)`
- `ActionMoveUnit(unit_id: str, target_region_id: int, target_latitude: float, target_longitude: float)`
- `ActionUpdateBudget(country_tag: str, allocations: dict)`

### Events Schema (`src/shared/events.py`)
- `GameEvent`: Base class.
- `EventNewDay(day: int, month: int, year: int)`: Fired at 00:00.
- `EventNewHour(hour: int, total_minutes: int)`: Fired every in-game hour.
- `EventRealSecond(game_seconds_passed: float, is_paused: bool)`: Fired at 1Hz real time.

## Success Criteria

- **SC-001**: Framerate Decoupling: UI rendering stays at 60+ FPS while server process runs heavy simulation at 10 TPS.
- **SC-002**: IPC Overhead: Arrow IPC serialization and queue transfer complete under 3ms per frame.
- **SC-003**: Reliable Lifecycle: 100% of session shutdowns terminate background processes without leaving zombie Python processes.

## Assumptions & Dependencies

- **Assumption**: PyArrow Arrow IPC streaming (`to_ipc()` / `from_ipc()`) handles zero-copy dataframe serialization.
- **Dependency**: Python `multiprocessing` library handles process spawning.
