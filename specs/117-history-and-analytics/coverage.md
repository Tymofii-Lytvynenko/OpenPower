# History and Analytics Coverage

## Functional requirements

| Requirement | Implementation and evidence |
| --- | --- |
| FR-001 | Default/configured country, region, relationship, military, demographic, economic, political, diplomatic, strategic indicators are measured in `modules/base/systems/world/history_system.py`; `test_history_records_authoritative_and_derived_metrics_without_changing_sources` and `test_history_aggregates_units_by_the_production_owner_field`. |
| FR-002 | Typed snapshot schema contains identity, value/unit, game minute/tick, boundary, confidence, completeness, kind, and schema version in `modules/base/schema.py`; initial/derived/missing row assertions in `tests/test_history_system.py`. |
| FR-003 | Definition schema and `_compact_group` apply configured interval, retention, cap, and deterministic downsampling; compaction boundary tests in `tests/test_history_system.py`. |
| FR-004 | `HistoryPanel` supports line/step trends, range/granularity, units, gaps, and current value; trend/no-gap-bridging regression in `tests/test_history_panel.py`. |
| FR-005 | `HistoryQueryService.compare` uses a common boundary and reports unit compatibility, relative-index basis, and unavailable series; mixed-unit and unit-transition tests in `tests/test_history_system.py`. |
| FR-006 | `rank` reports common boundary, direction, deterministic subject-ID tie rule, freshness, incompatible units, and exclusions; `test_history_queries_are_deterministic_and_expose_missing_units_and_ties`, boundary/unit ranking tests, and panel ranking regression. |
| FR-007 | Relation-value samples and domain treaty/war/recognition/diplomatic events are surfaced by relationship timelines; `test_history_relationship_timeline_includes_war_treaty_occupation_and_losses`. |
| FR-008 | Journal evidence preserves event payload, participants, occupation, battle loss and peace details; the same relationship timeline regression covers war end, treaty, occupation, and battle. |
| FR-009 | Journal payload source references and economic cause records are persisted once and rendered as evidence; `test_history_journal_and_economic_cause_events_are_persisted_once`; no cause is synthesized when absent. |
| FR-010 | Snapshot/event schemas distinguish value kind, confidence, completeness, missing and stale records; query/panel tests verify missing and incompatible data remain visible/excluded, not coerced to zero. |
| FR-011 | The recorder observes authoritative revisions independent of actor/controller and sorts deterministic identities; deterministic ordered continuation is covered by save/load/replay regression. |
| FR-012 | IPC and save/load retain definitions, series index, snapshots, event cursor, and deterministic continuation; `test_history_survives_state_snapshot_roundtrip_without_replaying_events` and `test_history_survives_save_load_and_deterministic_replay_continuation`. |
| FR-013 | Panel provides graph, comparison, ranking, relationship/event timeline, and CSV clipboard export; presenter regressions cover UI projection and export service output. |
| FR-014 | Stable IDs and time/tick/ID ordering, deterministic downsampling, rank tie rules, and replay equality are asserted by focused tests. |
| FR-015 | Recorder compares source table revisions and next due boundaries, skipping unchanged values; `test_history_records_only_changed_or_due_values_and_marks_missing_data`; the scale test exercises the indexed query path. |

## Success criteria

| Criterion | Evidence/status |
| --- | --- |
| SC-001 | Configured examples, change boundary, due boundary, removed subject/missing marker covered by `tests/test_history_system.py`; full indicator catalog still requires the focused suite. |
| SC-002 | Query and panel tests cover unit/source/completeness, current value, missing gaps, and freshness; manual visual acceptance remains open. |
| SC-003 | Common-boundary compare/rank, unit normalization limits, tie ordering, unavailable and stale/incompatible exclusions covered by tests. |
| SC-004 | Controlled war/treaty/occupation/battle events are chronologically returned; verified in relationship timeline test. |
| SC-005 | IPC, disk save/load, and identical continuation are covered by history persistence tests; gameplay source values are unchanged by the recorder test. |
| SC-006 | Panel surfaces change time and recorded source/cause; human 60-second workflow remains pending because no desktop game session was available. |
| SC-007 | Ranking over 10 million snapshots last measured at 2.67 ms (<500 ms) using the revision-matched series index. Deterministic per-series compaction is tested. Aggregate storage budget and a 10-million-row recording/compaction measurement are undefined/unverified; see the open issue in `research.md`. No optimization iterations were spent on this unmeasured gate. |

## Scope

This feature does not include the game editor or multiplayer, per [implementation-scope.md](../implementation-scope.md). The ordinary gameplay history panel remains in scope.
