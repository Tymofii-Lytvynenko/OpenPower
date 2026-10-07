# History Analytics Contracts

## Simulation recorder

`HistorySystem` is registered as `base.history` in `modules/base/registration.py`, runs in `POST_PROCESS`, and depends on `base.campaign`. It reads declared gameplay/source tables and writes only `history_indicator_definitions`, `history_series_state`, `history_snapshots`, and `history_events`.

The recorder ensures default indicator definitions, measures configured indicators, emits an initial/change/due/missing observation when required, compacts touched series according to their retention policy, and appends previously unseen domain journal/economic-cause records. Repeated processing of unchanged state must not create duplicate observations or events.

## Client query service

`src.client.services.history_query_service.HistoryQueryService` is a read-only client service over the synchronized `GameState` tables.

| Method | Contract |
| --- | --- |
| `current_value(state, subject_type, subject_id, indicator_id)` | Returns availability, value, unit, and authoritative/derived/missing kind from current authoritative state tables. |
| `series(..., start_minute, end_minute, granularity_minutes, include_non_authoritative)` | Returns chronologically ordered samples; positive granularity chooses the last sample in each time bucket. |
| `compare(..., subject_ids, ..., granularity_minutes)` | Returns per-subject series, common evaluation-boundary values, units, missing subjects, and explicit optional relative-index basis. |
| `rank(..., descending)` | Returns rows at the common boundary, canonical unit, direction, ID tie rule, freshness, incompatible-unit subjects, and exclusions. |
| `relationship_timeline(state, country_a, country_b)` | Combines relation samples and attributable events in deterministic time/tick/ID order. |
| `event_timeline(...)` / `cause_trail(...)` | Returns only matching persisted evidence in the requested time and subject scope. Unknown causes are not inferred. |
| `export_csv(records)` | Returns a deterministic CSV representation of the selected records; an empty input returns an empty string. |

The query service and panel do not modify `GameState`, dispatch gameplay actions, or import module-layer simulation implementations.

## In-game panel

`HistoryPanel` is registered in the normal gameplay panel registry and opened from the in-game system bar. It exposes indicator/subject selection, time range, granularity, line/step trend, gaps, current value, comparison targets, optional indexed comparisons, rankings, event timelines, and clipboard CSV actions. This is gameplay analytics UI, not the excluded game editor.

## Persistence and synchronization

All four tables use the base typed schema registry and stable primary keys. Existing snapshot IPC and save/load serializers carry these rows and recorder cursors. Loading old saves with no history starts observations at the first supported update without changing current gameplay data.
