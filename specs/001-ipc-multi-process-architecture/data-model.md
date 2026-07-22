# Data Model: Multi-Process IPC Architecture

## Core Entity Schemas

### 1. `GameState` Container (`src/server/state.py`)
Central data structure containing all simulation tables and metadata.

- `tables`: `Dict[str, pl.DataFrame]` — Dynamic collection of Polars DataFrames (`regions`, `countries`, `units`, `countries_relations`, `countries_treaties`, `countries_wars`, `domestic_production`, `resource_ledger`).
- `time`: `TimeData` — Micro-component tracking game epoch progression.
- `globals`: `Dict[str, Any]` — Simulation metadata (`tick`, `game_speed`).
- `events`: `List[GameEvent]` — Transient event bus list cleared per tick.
- `current_actions`: `List[GameAction]` — Actions ingested during current tick.

### 2. `TimeData` Dataclass (`src/server/state.py`)
- `total_minutes`: `int` — Authoritative source of elapsed time from `GAME_EPOCH` (2001-01-01 00:00).
- `year`: `int` (default 2001)
- `month`: `int` (default 1)
- `day`: `int` (default 1)
- `hour`: `int` (default 0)
- `minute`: `int` (default 0)
- `date_str`: `str` — Pre-formatted UI string `"%Y-%m-%d %H:%M"`.
- `speed_level`: `int` — Active speed level (1 to 5).
- `is_paused`: `bool` — Simulation pause flag.

### 3. Arrow IPC Binary Payload Schema (`GameState.to_ipc()`)
```json
{
  "tables": {
    "regions": "<bytes>",
    "countries": "<bytes>",
    "units": "<bytes>",
    "countries_relations": "<bytes>",
    "countries_treaties": "<bytes>",
    "countries_wars": "<bytes>",
    "domestic_production": "<bytes>"
  },
  "time": "<TimeData dataclass>",
  "globals": {
    "tick": 1420,
    "game_speed": 1.0
  }
}
```
