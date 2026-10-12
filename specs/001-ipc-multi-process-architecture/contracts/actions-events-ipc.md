# Interface Contracts: Actions, Events & IPC Protocol

## 1. Action Queue Schema (`src/shared/actions.py`)

Player intent is represented by `GameAction` subclasses. The client wraps each action in a `CommandEnvelope` before queue transport; this table lists representative gameplay actions, not the exhaustive action catalog.

| Class Name | Constructor Signature | Primary Action Behavior |
| :--- | :--- | :--- |
| `ActionSetRegionOwner` | `(region_id: int, new_owner_tag: str)` | Reassigns `owner` and `controller` columns in `regions` table. |
| `ActionSetTax` | `(country_tag: str, new_tax_rate: float)` | Sets `personal_income_tax_rate` for target country. |
| `ActionSetGameSpeed` | `(speed_level: int)` | Updates `TimeData.speed_level` (1 to 5). |
| `ActionSetPaused` | `(is_paused: bool)` | Toggles `TimeData.is_paused`. |
| `ActionSaveGame` | `(save_name: str)` | Triggers atomic save writer (`SaveWriter`). |
| `ActionBuildUnit` | `(country_tag: str, unit_type: str, count: int)` | Deducts unit build cost and instantiates military division. |
| `ActionMoveUnit` | `(unit_id: str, target_region_id: int, target_lat: float, target_lon: float)` | Computes SLERP march track and sets destination. |
| `ActionUpdateBudget` | `(country_tag: str, allocations: dict)` | Updates 11 budget sector ratios (`budget_*_ratio`). |

## 2. Event Bus Schema (`src/shared/events.py`)

Core time signals generated during simulation ticks and delivered in `state.events`. Domain-specific transient and journaled events are defined by their feature contracts.

| Class Name | Attributes | Trigger Frequency |
| :--- | :--- | :--- |
| `EventNewDay` | `day: int, month: int, year: int` | Fired when hour wraps to 00:00. |
| `EventNewHour` | `hour: int, total_minutes: int` | Fired on every in-game minute 0. |
| `EventRealSecond` | `game_seconds_passed: float, is_paused: bool` | Fired at 1Hz real time for economic heartbeats. |

## 3. IPC Message Queue Contracts

- **`action_queue`**: Enqueues `CommandEnvelope` objects containing `GameAction`, plus string control commands (`"SHUTDOWN"`, `"SAVE_MAP_CHANGES"`). The server drains it before ticking and between fixed steps in a catch-up batch.
- **`state_queue`**: Enqueues protocol-versioned Arrow IPC full snapshots and table deltas. Protocol version 3 also supports append-only tails for `history_snapshots` while the acknowledged prefix is unchanged; compaction falls back to a changed-table replacement. Delta bases remain cumulative from the last acknowledged sequence if queue backpressure drops a packet.
- **`progress_queue`**: Enqueues diagnostic tuples `(type_str, float_progress, status_str)`.
- **`snapshot_ack_queue`**: Enqueues decoded snapshot sequences so the server can advance the delta base only after successful reconstruction.

`src/shared/snapshots.py` owns the protocol-versioned full/delta packet format. Full packets include all current tables and journal state; deltas include changed table payloads, removed table names, append tails, and journal additions. `src/client/services/snapshot_inbox.py` decodes packets away from the render callback and acknowledges them only after successful reconstruction. `src/server/launcher.py` creates all four queues and `src/server/server_process.py` is their authoritative consumer/producer.

The server drains `snapshot_ack_queue` before ticking and between catch-up steps. It encodes and offers a snapshot after each completed fixed step; if the bounded state queue is full, the dropped packet does not advance the acknowledgement base, so subsequent deltas remain cumulative from the last successfully decoded sequence.
