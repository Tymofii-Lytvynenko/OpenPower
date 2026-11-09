import polars as pl

from modules.base.systems.world.history_system import HistorySystem


def test_next_due_uses_the_earliest_matching_series_and_maximum_without_matches() -> None:
    definition = {"id": "gdp"}
    series = {
        "late": {"indicator_id": "gdp", "next_sample_at_minute": 40},
        "early": {"indicator_id": "gdp", "next_sample_at_minute": 12},
        "other": {"indicator_id": "population", "next_sample_at_minute": 3},
    }

    assert HistorySystem._next_due(series, definition) == 12
    assert HistorySystem._next_due({}, definition) == 2**63 - 1


def test_same_value_falls_back_to_native_equality_for_non_numeric_values() -> None:
    assert HistorySystem._same_value("unknown", "unknown") is True
    assert HistorySystem._same_value("unknown", "other") is False


def test_empty_history_row_operations_preserve_table_schema() -> None:
    table = pl.DataFrame({"value": [1]})

    assert HistorySystem._append(table, []) is table
    empty = HistorySystem._frame(table, [])
    assert empty.columns == table.columns
    assert empty.is_empty()


def test_event_minute_skips_invalid_fields_and_reads_the_next_timestamp() -> None:
    payload = {"at_minute": "invalid", "started_at_minute": "17"}

    assert HistorySystem._event_minute(payload, fallback=2) == 17
