# Interface Contracts: Actions, Events & IPC Protocol

## 1. Action Queue Schema (`src/shared/actions.py`)

All player intent dispatches implement the `GameAction` base class.

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

Signals generated during simulation system ticks and delivered in `state.events`.

| Class Name | Attributes | Trigger Frequency |
| :--- | :--- | :--- |
| `EventNewDay` | `day: int, month: int, year: int` | Fired when hour wraps to 00:00. |
| `EventNewHour` | `hour: int, total_minutes: int` | Fired on every in-game minute 0. |
| `EventRealSecond` | `game_seconds_passed: float, is_paused: bool` | Fired at 1Hz real time for economic heartbeats. |

## 3. IPC Message Queue Contracts

- **`action_queue`**: Enqueues `GameAction` objects or string control commands (`"SHUTDOWN"`, `"SAVE_MAP_CHANGES"`).
- **`state_queue`**: Enqueues Apache Arrow IPC serialized `dict` payload. Client drains all stale items, reading only the latest snapshot.
- **`progress_queue`**: Enqueues diagnostic tuples `(type_str, float_progress, status_str)`.
