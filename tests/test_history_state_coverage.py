import polars as pl

from modules.base.schema import build_base_schema_registry
from modules.base.systems.world.history_system import HistorySystem
from src.shared.state import GameState


def _regional_state() -> GameState:
    state = GameState(
        tables={
            "regions": pl.DataFrame(
                {
                    "id": [1],
                    "owner": ["USA"],
                    "pop_14": [10],
                    "pop_15_64": [60],
                    "pop_65": [5],
                }
            )
        }
    )
    registry = build_base_schema_registry()
    registry.capture_state(state)
    registry.ensure_state(state)
    return state


def test_defaults_and_observation_recording_return_for_missing_or_disabled_inputs() -> None:
    system = HistorySystem()
    system._ensure_defaults(GameState(tables={}))

    state_without_units = GameState(
        tables={
            "history_indicator_definitions": pl.DataFrame(
                schema={"id": pl.String}
            )
        }
    )
    system._ensure_defaults(state_without_units)
    assert state_without_units.tables["history_indicator_definitions"].is_empty()

    system._record_observations(GameState(tables={}))
    disabled_state = GameState(
        tables={
            "history_indicator_definitions": pl.DataFrame(
                {"id": ["disabled"], "enabled": [False]}
            ),
            "history_series_state": pl.DataFrame(),
            "history_snapshots": pl.DataFrame(),
        }
    )
    system._record_observations(disabled_state)


def test_omitted_removed_subjects_get_an_entity_removed_snapshot() -> None:
    state = _regional_state()
    system = HistorySystem()
    state.globals["tick"] = 1
    system.update(state, 0.0)

    definitions = state.tables["history_indicator_definitions"]
    rows = definitions.to_dicts()
    population = next(row for row in rows if row["id"] == "region.population")
    population["missing_data_policy"] = "omit"
    state.update_table(
        "history_indicator_definitions",
        pl.DataFrame(rows, schema=definitions.schema),
    )
    state.update_table("regions", state.tables["regions"].head(0))
    state.globals["tick"] = 2
    system.update(state, 0.0)

    removed = [
        row
        for row in state.tables["history_snapshots"].to_dicts()
        if row["indicator_id"] == "region.population" and row["subject_id"] == "1"
    ]
    assert removed[-1]["value"] is None
    assert removed[-1]["source_boundary"] == "entity_removed"
    assert removed[-1]["completeness"] == "missing"


def test_fingerprints_and_measurements_reject_incomplete_contracts() -> None:
    system = HistorySystem()
    assert system._observation_fingerprint(
        GameState(tables={}), {"source_table": "missing"}
    ) is None
    assert system._observation_fingerprint(
        GameState(tables={"countries_relations": pl.DataFrame({"source": ["USA"]})}),
        {"source_table": "countries_relations", "derivation": "overall_relations"},
    ) is None
    assert system._observation_fingerprint(
        GameState(
            tables={
                "countries": pl.DataFrame({"id": ["USA"]}),
                "countries_relations": pl.DataFrame({"source": ["USA"]}),
            }
        ),
        {"source_table": "countries_relations", "derivation": "overall_relations"},
    ) is None
    assert system._observation_fingerprint(
        GameState(tables={"measurement": pl.DataFrame({"value": [1.0]})}),
        {"source_table": "measurement"},
    ) is None

    assert system._measure_definition(
        GameState(tables={}), {"derivation": "region_population"}
    ) == ({}, {})
    assert system._measure_definition(
        GameState(tables={}), {"source_table": "missing"}
    ) == ({}, {})
    assert system._measure_definition(
        GameState(tables={"measurement": pl.DataFrame({"value": [1.0]})}),
        {
            "source_table": "measurement",
            "source_field": "value",
            "subject_id_field": "absent",
        },
    ) == ({}, {})


def test_generic_measurements_skip_blank_subject_and_relationship_ids() -> None:
    state = GameState(
        tables={
            "measurement": pl.DataFrame(
                {
                    "subject": ["", "USA", "USA"],
                    "related": ["CAN", "", "CAN"],
                    "value": [1.0, 2.0, 3.0],
                }
            )
        }
    )
    system = HistorySystem()

    assert system._measure_definition(
        state,
        {
            "source_table": "measurement",
            "source_field": "value",
            "subject_id_field": "subject",
            "aggregation": "sum",
        },
    )[0] == {"USA": 5.0}
    assert system._measure_definition(
        state,
        {
            "source_table": "measurement",
            "source_field": "value",
            "subject_id_field": "subject",
            "related_id_field": "related",
            "subject_type": "relationship",
            "aggregation": "sum",
        },
    )[0] == {"CAN|USA": 3.0}


def test_journal_recording_handles_missing_tables_cursor_overflow_and_duplicates() -> None:
    system = HistorySystem()
    system._record_journal_events(GameState(tables={}))

    cursor_state = GameState(
        tables={"history_events": pl.DataFrame(schema={"id": pl.String})}
    )
    cursor_state.globals["history_journal_cursor"] = 3
    system._record_journal_events(cursor_state)
    assert cursor_state.globals["history_journal_cursor"] == 0

    duplicate_state = GameState(
        tables={"history_events": pl.DataFrame({"id": ["journal:duplicate"]})}
    )
    duplicate_state.journal.domain_events.append(
        {"event_id": "duplicate", "payload": {}}
    )
    system._record_journal_events(duplicate_state)
    assert duplicate_state.tables["history_events"].height == 1
    assert duplicate_state.globals["history_journal_cursor"] == 1


def test_compaction_preserves_empty_inputs_and_groups_under_the_cap() -> None:
    system = HistorySystem()
    state = GameState(
        tables={
            "history_snapshots": pl.DataFrame(),
            "history_series_state": pl.DataFrame(),
        }
    )
    system._compact(state, [], {"series"}, now=10)

    group = pl.DataFrame(
        {
            "id": ["one", "two"],
            "game_minute": [8, 9],
            "tick": [1, 1],
        }
    )
    kept = HistorySystem._compact_group(group, now=10, retention=5, cap=2)
    assert kept.get_column("id").to_list() == ["one", "two"]
