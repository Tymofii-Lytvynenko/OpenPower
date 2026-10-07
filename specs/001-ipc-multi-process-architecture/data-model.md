# Data Model: Multi-Process IPC Architecture

## Core Entity Schemas

### 1. `GameState` Container (`src/shared/state.py`)
Central data structure containing all simulation tables and metadata.

- `tables`: `Dict[str, pl.DataFrame]` — Dynamic collection of Polars DataFrames (`regions`, `countries`, `units`, `countries_relations`, `countries_treaties`, `countries_wars`, `domestic_production`, `resource_ledger`).
- `time`: `TimeData` — Micro-component tracking game epoch progression.
- `globals`: `Dict[str, Any]` — Simulation metadata (`tick`, `game_speed`).
- `events`: `List[GameEvent]` — Transient event bus list cleared per tick.
- `journal`: `JournalState` — Persistent domain events and command results.
- `determinism`: `DeterminismState` — Replay-safe random state.
- `_table_revisions`: `Dict[str, int]` — Internal revisions used to select changed tables for snapshot deltas.
- `current_actions`: `List[GameAction]` — Actions ingested during current tick.

### 2. `TimeData` Dataclass (`src/shared/state.py`)
- `total_minutes`: `int` — Authoritative source of elapsed time from `GAME_EPOCH` (2001-01-01 00:00).
- `year`: `int` (default 2001)
- `month`: `int` (default 1)
- `day`: `int` (default 1)
- `hour`: `int` (default 0)
- `minute`: `int` (default 0)
- `date_str`: `str` — Pre-formatted UI string `"%Y-%m-%d %H:%M"`.
- `speed_level`: `int` — Active speed level (1 to 5).
- `is_paused`: `bool` — Simulation pause flag.

### 3. Acknowledged Arrow IPC Snapshot Payload (`GameState.to_ipc()`)
```json
{
  "protocol_version": 2,
  "kind": "full",
  "sequence": 1,
  "base_sequence": 0,
  "tables": {
    "regions": "<bytes>",
    "countries": "<bytes>",
    "units": "<bytes>",
    "countries_relations": "<bytes>",
    "countries_treaties": "<bytes>",
    "countries_wars": "<bytes>",
    "domestic_production": "<bytes>"
  },
  "removed_tables": [],
  "table_revisions": {"regions": 1, "countries": 1},
  "time": "<TimeData dataclass>",
  "globals": {
    "tick": 1420,
    "game_speed": 1.0
  },
  "system_state": "<persistent system state>",
  "determinism": "<deterministic random state>",
  "journal": "<full journal for full snapshots>",
  "events": "<current transient events>"
}
```

Table payloads are Polars Arrow IPC byte buffers. The initial full snapshot carries all tables; later delta packets carry only changed table revisions, removed-table names, and journal additions relative to the last acknowledged base sequence. Delta packets carry `domain_events` and `command_results` instead of a full `journal` field.
