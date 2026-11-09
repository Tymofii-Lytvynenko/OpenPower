import csv
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

from src.client.services.history_query_service import HistoryQueryService


def state_with(tables=None, *, revisions=None, globals_=None):
    return SimpleNamespace(
        tables=tables or {},
        table_revisions=revisions,
        globals=globals_ or {},
    )


def definition(indicator_id="metric", **overrides):
    return {
        "id": indicator_id,
        "unit": "count",
        "derivation": "",
        "source_table": "source",
        "subject_id_field": "subject_id",
        "source_field": "value",
        "related_id_field": "",
        "filter_field": "",
        "filter_value": "",
        "aggregation": "last",
        **overrides,
    }


def snapshot(identifier, subject, minute, value, *, unit="USD", kind="authoritative", completeness="complete", tick=0):
    return {
        "id": identifier,
        "subject_type": "country",
        "subject_id": subject,
        "indicator_id": "metric",
        "value": value,
        "unit": unit,
        "game_minute": minute,
        "tick": tick,
        "completeness": completeness,
        "value_kind": kind,
    }


def index_row(**overrides):
    return {
        "subject_type": "country",
        "subject_id": "USA",
        "indicator_id": "metric",
        "unit": "USD",
        "latest_value": 10.0,
        "latest_snapshot_id": "snapshot-1",
        "latest_source_boundary": "source",
        "latest_confidence": 1.0,
        "latest_value_kind": "authoritative",
        "last_sample_minute": 5,
        "last_sample_tick": 2,
        "sample_count": 1,
        "completeness": "complete",
        **overrides,
    }


def test_current_value_reports_missing_definitions_and_missing_authoritative_sources():
    service = HistoryQueryService()
    empty_definitions = pl.DataFrame(schema={"id": pl.String})
    definitions = pl.DataFrame([definition()])

    assert service.current_value(state_with(), "country", "USA", "metric")["available"] is False
    assert service.current_value(
        state_with({"history_indicator_definitions": empty_definitions}),
        "country",
        "USA",
        "metric",
    )["unit"] == ""
    assert service.current_value(
        state_with({"history_indicator_definitions": definitions}), "country", "USA", "other"
    )["value_kind"] == "missing"

    missing_table = service.current_value(
        state_with({"history_indicator_definitions": definitions}), "country", "USA", "metric"
    )
    empty_table = service.current_value(
        state_with({
            "history_indicator_definitions": definitions,
            "source": pl.DataFrame(schema={"subject_id": pl.String, "value": pl.Float64}),
        }),
        "country",
        "USA",
        "metric",
    )
    invalid_columns = service.current_value(
        state_with({
            "history_indicator_definitions": definitions,
            "source": pl.DataFrame({"subject": ["USA"], "amount": [5.0]}),
        }),
        "country",
        "USA",
        "metric",
    )
    assert missing_table == empty_table == invalid_columns == {
        "available": False,
        "value": None,
        "unit": "count",
        "value_kind": "missing",
    }


@pytest.mark.parametrize(
    ("aggregation", "expected"),
    [("count", 3.0), ("sum", 4.0), ("mean", 2.0), ("max", 3.0), ("last", 3.0)],
)
def test_current_value_filters_rows_and_applies_declared_aggregation(aggregation, expected):
    rows = pl.DataFrame(
        {
            "subject_id": ["USA", "USA", "USA", "USA", "CAN"],
            "kind": ["gdp", "gdp", "other", "gdp", "gdp"],
            "value": [1.0, 3.0, 99.0, float("nan"), 20.0],
        }
    )
    tables = {
        "history_indicator_definitions": pl.DataFrame(
            [definition(filter_field="kind", filter_value="gdp", aggregation=aggregation)]
        ),
        "source": rows,
    }

    result = HistoryQueryService().current_value(state_with(tables), "country", "USA", "metric")

    assert result == {
        "available": True,
        "value": expected,
        "unit": "count",
        "value_kind": "authoritative",
    }


def test_current_value_normalizes_relationship_pairs_and_rejects_non_finite_samples():
    tables = {
        "history_indicator_definitions": pl.DataFrame(
            [
                definition(
                    subject_id_field="source",
                    related_id_field="target",
                    aggregation="mean",
                )
            ]
        ),
        "source": pl.DataFrame(
            {
                "source": ["USA", "CAN", "USA", "USA"],
                "target": ["CAN", "USA", "MEX", "CAN"],
                "value": [10.0, 20.0, 100.0, float("inf")],
            }
        ),
    }

    result = HistoryQueryService().current_value(
        state_with(tables), "relationship", "can|usa", "metric"
    )

    assert result["value"] == 15.0
    assert result["value_kind"] == "authoritative"


def test_current_value_derives_population_from_supported_partial_schema():
    service = HistoryQueryService()
    per_capita = definition("per-capita", derivation="gdp_per_capita")
    region_population = definition("region-pop", derivation="region_population")
    country_population = definition("country-pop", derivation="country_population")
    tables = {
        "history_indicator_definitions": pl.DataFrame([per_capita, region_population, country_population]),
        "countries": pl.DataFrame({"id": ["USA"], "gdp": [1000.0]}),
        "regions": pl.DataFrame({
            "id": ["1", "2"],
            "owner": ["USA", "CAN"],
            "owner_tag": ["USA", "CAN"],
            "pop_15_64": [25.0, 15.0],
        }),
    }

    per_capita_value = service.current_value(state_with(tables), "country", "USA", "per-capita")
    one_region = service.current_value(state_with(tables), "region", "1", "region-pop")
    country_total = service.current_value(state_with(tables), "country", "USA", "country-pop")
    assert per_capita_value["value"] == 40.0
    assert one_region["value"] == 25.0
    assert country_total["value"] == 25.0


def test_current_value_returns_unavailable_for_incomplete_derived_inputs():
    service = HistoryQueryService()
    definitions = pl.DataFrame(
        [
            definition("per-capita", derivation="gdp_per_capita"),
            definition("region-pop", derivation="region_population"),
            definition("country-pop", derivation="country_population"),
            definition("resource", derivation="resource_coverage"),
        ]
    )
    base = {"history_indicator_definitions": definitions}

    cases = [
        ("per-capita", {**base, "countries": pl.DataFrame({"id": ["USA"]}), "regions": pl.DataFrame({"id": ["1"]})}),
        ("per-capita", {**base, "countries": pl.DataFrame({"id": ["USA"], "gdp": [1.0]}), "regions": pl.DataFrame({"id": ["1"]})}),
        ("per-capita", {**base, "countries": pl.DataFrame({"id": ["USA"], "gdp": [1.0]}), "regions": pl.DataFrame({"owner": ["USA"], "pop_14": [0.0]})}),
        ("region-pop", {**base, "regions": pl.DataFrame({"owner": ["USA"], "pop_14": [1.0]})}),
        ("region-pop", {**base, "regions": pl.DataFrame({"id": ["USA"]})}),
        ("country-pop", {**base, "regions": pl.DataFrame({"id": ["1"], "pop_14": [1.0]})}),
        ("country-pop", {**base, "regions": pl.DataFrame({"owner": ["USA"]})}),
        ("resource", base),
    ]

    for indicator, tables in cases:
        result = service.current_value(state_with(tables), "country", "USA", indicator)
        assert result["available"] is False
        assert result["unit"] == "count"


def test_region_population_is_unavailable_when_the_requested_region_is_absent():
    state = state_with({
        "history_indicator_definitions": pl.DataFrame([
            definition("region-pop", derivation="region_population")
        ]),
        "regions": pl.DataFrame({"id": ["1"], "pop_14": [25.0]}),
    })

    result = HistoryQueryService().current_value(state, "region", "USA", "region-pop")

    assert result["available"] is False
    assert result["value"] is None


def test_current_value_counts_relationship_rows_and_handles_unusable_values():
    rows = pl.DataFrame(
        {
            "country": ["USA", "USA", "CAN"],
            "subject_id": ["USA", "USA", "CAN"],
            "value": [None, "bad", "4.0"],
        }
    )
    count_definition = definition(aggregation="count")
    count_state = state_with({
        "history_indicator_definitions": pl.DataFrame([count_definition]),
        "source": rows,
    })
    count_value = HistoryQueryService().current_value(count_state, "country", "USA", "metric")
    assert count_value["value"] == 2.0

    sum_definition = definition(source_field="value", aggregation="sum")
    sum_state = state_with({
        "history_indicator_definitions": pl.DataFrame([sum_definition]),
        "source": pl.DataFrame({"subject_id": ["USA", "USA"], "value": ["bad", None]}),
    })
    assert HistoryQueryService().current_value(sum_state, "country", "USA", "metric")["available"] is False


def test_current_value_preserves_region_subject_matching_for_authoritative_rows():
    state = state_with({
        "history_indicator_definitions": pl.DataFrame([definition()]),
        "source": pl.DataFrame({"subject_id": ["1", "USA"], "value": [25.0, 90.0]}),
    })

    result = HistoryQueryService().current_value(state, "region", "1", "metric")

    assert result["value"] == 25.0


def test_series_filters_time_authority_and_keeps_last_sample_per_bucket():
    table = pl.DataFrame(
        [
            snapshot("s1", "USA", 4, 4.0),
            snapshot("s2", "USA", 5, 5.0, kind="derived"),
            snapshot("s3", "USA", 7, 7.0),
            snapshot("s4", "USA", 10, 10.0),
            snapshot("other", "CAN", 6, 6.0),
        ]
    )
    state = state_with({"history_snapshots": table})

    rows = HistoryQueryService().series(
        state,
        "country",
        "USA",
        "metric",
        start_minute=5,
        end_minute=10,
        granularity_minutes=5,
        include_non_authoritative=False,
    )

    assert [row["id"] for row in rows] == ["s3", "s4"]


def test_series_returns_empty_for_absent_or_empty_snapshot_tables():
    service = HistoryQueryService()
    empty = pl.DataFrame(schema={
        "subject_type": pl.String,
        "subject_id": pl.String,
        "indicator_id": pl.String,
        "game_minute": pl.Int64,
        "tick": pl.Int64,
        "id": pl.String,
    })

    assert service.series(state_with(), "country", "USA", "metric") == []
    assert service.series(state_with({"history_snapshots": empty}), "country", "USA", "metric") == []


def test_compare_handles_empty_subjects_and_rows_without_comparable_values():
    service = HistoryQueryService()
    empty_state = state_with()
    empty = service.compare(empty_state, "country", [], "metric")
    assert empty["series"] == {}
    assert empty["unit"] == ""
    assert empty["evaluation_minute"] is None
    assert empty["freshness_by_subject"] == {}

    table = pl.DataFrame(
        [
            snapshot("u1", "USA", 2, 0.0),
            snapshot("u2", "USA", 4, float("inf")),
            snapshot("c1", "CAN", 4, None, completeness="missing"),
        ]
    )
    compare = service.compare(state_with({"history_snapshots": table}), "country", ["USA", "CAN", "MEX"], "metric")
    assert compare["evaluation_minute"] == 4
    assert compare["normalization_unavailable_subjects"] == ["CAN", "MEX", "USA"]
    assert compare["common_unavailable_subjects"] == ["MEX"]
    assert compare["normalized_common_values"] == {}


def test_compare_omits_non_finite_normalized_values():
    rows = pl.DataFrame([
        snapshot("u-first", "USA", 1, 1e-308),
        snapshot("u-last", "USA", 2, 1e308),
        snapshot("c-latest", "CAN", 2, 1.0),
    ])

    result = HistoryQueryService().compare(
        state_with({"history_snapshots": rows}), "country", ["USA", "CAN"], "metric"
    )

    assert "USA" not in result["normalized_common_values"]
    assert result["normalized_common_values"]["CAN"]["value"] == 100.0


def test_rank_handles_missing_snapshots_and_falls_back_to_common_boundary_scan():
    service = HistoryQueryService()
    missing = service.rank(state_with(), "metric", descending=False)
    assert missing["rows"] == []
    assert missing["direction"] == "ascending"

    table = pl.DataFrame(
        [
            snapshot("u1", "USA", 2, 9.0),
            snapshot("u2", "USA", 5, 3.0),
            snapshot("c1", "CAN", 5, 3.0),
            snapshot("m1", "MEX", 8, 1.0),
        ]
    )
    ranking = service.rank(
        state_with({"history_snapshots": table}),
        "metric",
        descending=False,
        start_minute=3,
        end_minute=8,
    )
    assert ranking["evaluation_minute"] == 5
    assert [row["subject_id"] for row in ranking["rows"]] == ["CAN", "USA"]
    assert ranking["ties"] == [{"value": 3.0, "unit": "USD", "subjects": ["CAN", "USA"]}]
    assert ranking["excluded"] == ["MEX"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, False), ("bad", False), (0, False), (-2, False), (float("inf"), False), (float("nan"), False), (1, True)],
)
def test_value_validation_rejects_missing_invalid_and_non_positive_samples(value, expected):
    assert HistoryQueryService._positive_finite(value) is expected


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"value": None, "completeness": "complete"}, False),
        ({"value": 1.0, "completeness": "missing"}, False),
        ({"value": 1.0, "completeness": "stale"}, False),
        ({"value": "bad", "completeness": "complete"}, False),
        ({"value": float("inf"), "completeness": "complete"}, False),
        ({"value": 1.0, "completeness": "complete"}, True),
    ],
)
def test_valid_value_row_checks_presence_completeness_and_finiteness(row, expected):
    assert HistoryQueryService._valid_value_row(row) is expected


def test_indicator_unit_uses_only_a_matching_definition_with_a_unit_column():
    empty = pl.DataFrame(schema={"id": pl.String, "unit": pl.String})
    definitions = pl.DataFrame({"id": ["other", "metric"], "unit": ["people", "USD"]})

    assert HistoryQueryService._indicator_unit(state_with(), "metric") == ""
    assert HistoryQueryService._indicator_unit(state_with({"history_indicator_definitions": empty}), "metric") == ""
    assert HistoryQueryService._indicator_unit(
        state_with({"history_indicator_definitions": pl.DataFrame({"id": ["metric"]})}), "metric"
    ) == ""
    assert HistoryQueryService._indicator_unit(
        state_with({"history_indicator_definitions": definitions}), "metric"
    ) == "USD"


def test_indexed_latest_rank_rows_rejects_stale_or_incomplete_indexes():
    snapshots = pl.DataFrame([snapshot("s1", "USA", 5, 10.0)])
    state = state_with()
    assert HistoryQueryService._indexed_latest_rank_rows(
        state, snapshots, "metric", "country", None, None
    ) is None

    required = index_row()
    missing_column = pl.DataFrame([{key: value for key, value in required.items() if key != "unit"}])
    state = state_with({"history_series_state": missing_column})
    assert HistoryQueryService._indexed_latest_rank_rows(
        state, snapshots, "metric", "country", None, None
    ) is None

    stale_state = state_with(
        {"history_series_state": pl.DataFrame([required])},
        revisions={"history_snapshots": 2},
        globals_={"history_series_snapshot_revision": 1},
    )
    assert HistoryQueryService._indexed_latest_rank_rows(
        stale_state, snapshots, "metric", "country", None, None
    ) is None

    mismatch = state_with({"history_series_state": pl.DataFrame([index_row(sample_count=2)])})
    assert HistoryQueryService._indexed_latest_rank_rows(
        mismatch, snapshots, "metric", "country", None, None
    ) is None


@pytest.mark.parametrize(
    ("rows", "start", "end", "expected"),
    [
        ([index_row(sample_count=0)], None, None, (None, [], [])),
        ([index_row(last_sample_minute=4)], 5, None, (None, [], [])),
        ([index_row(last_sample_minute=5), index_row(subject_id="CAN", last_sample_minute=6)], None, None, None),
        ([index_row(latest_snapshot_id="")], None, None, None),
        ([index_row(last_sample_minute=10)], None, 5, None),
    ],
)
def test_indexed_latest_rank_rows_validates_index_coverage_and_boundaries(rows, start, end, expected):
    sample_count = sum(row["sample_count"] for row in rows)
    snapshots = pl.DataFrame([snapshot(f"s{i}", f"C{i}", i, 1.0) for i in range(sample_count)])
    state = state_with({"history_series_state": pl.DataFrame(rows)})

    result = HistoryQueryService._indexed_latest_rank_rows(
        state, snapshots, "metric", "country", start, end
    )

    if expected is None:
        assert result is None
    else:
        assert result == expected


def test_indexed_latest_rank_rows_builds_snapshot_views_when_index_is_current():
    state = state_with({"history_series_state": pl.DataFrame([index_row()])})
    snapshots = pl.DataFrame([snapshot("s1", "USA", 5, 10.0)])

    result = HistoryQueryService._indexed_latest_rank_rows(
        state, snapshots, "metric", "country", None, None
    )

    assert result[0] == 5
    assert result[1][0]["id"] == "snapshot-1"
    assert result[1][0]["value"] == 10.0
    assert result[2] == []


def test_latest_snapshot_rows_at_common_boundary_tracks_subjects_without_a_sample():
    empty = pl.DataFrame(schema={
        "id": pl.String,
        "subject_id": pl.String,
        "game_minute": pl.Int64,
        "tick": pl.Int64,
        "value": pl.Float64,
    })
    result = HistoryQueryService._latest_snapshot_rows_at_common_boundary(empty)
    assert result[0] is None and result[1].is_empty() and result[2] == []

    no_minute = pl.DataFrame(
        {"id": ["s"], "subject_id": ["USA"], "game_minute": [None], "tick": [1], "value": [1.0]},
        schema_overrides={"game_minute": pl.Int64},
    )
    assert HistoryQueryService._latest_snapshot_rows_at_common_boundary(no_minute)[0] is None

    samples = pl.DataFrame(
        [
            snapshot("u1", "USA", 3, 3.0),
            snapshot("u2", "USA", 5, 5.0),
            snapshot("c1", "CAN", 5, 4.0),
            snapshot("m1", "MEX", 8, 8.0),
        ]
    )
    minute, rows, missing = HistoryQueryService._latest_snapshot_rows_at_common_boundary(samples)
    assert minute == 5
    assert set(rows.get_column("subject_id").to_list()) == {"USA", "CAN"}
    assert missing == ["MEX"]


def test_event_timeline_filters_subject_relationships_and_time_boundaries():
    service = HistoryQueryService()
    events = pl.DataFrame(
        [
            {"id": "early", "subject_type": "country", "subject_id": "USA", "related_country_ids_json": '["CAN"]', "game_minute": 7, "tick": 1},
            {"id": "late", "subject_type": "country", "subject_id": "USA", "related_country_ids_json": '["CAN"]', "game_minute": 12, "tick": 1},
            {"id": "inside", "subject_type": "country", "subject_id": "USA", "related_country_ids_json": '["CAN"]', "game_minute": 8, "tick": 2},
            {"id": "other", "subject_type": "country", "subject_id": "MEX", "related_country_ids_json": "bad", "game_minute": 8, "tick": 1},
            {"id": "war", "subject_type": "war", "subject_id": "war-1", "related_country_ids_json": '["USA", "CAN"]', "game_minute": 9, "tick": 1},
        ]
    )
    state = state_with({"history_events": events})

    selected = service.event_timeline(
        state,
        subject_type="country",
        subject_id="CAN",
        country_ids=["USA", "CAN"],
        start_minute=8,
        end_minute=9,
    )

    assert [row["id"] for row in selected] == ["inside"]
    assert service.event_timeline(state_with(), country_ids=["USA"]) == []
    empty = pl.DataFrame(schema={"id": pl.String})
    assert service.event_timeline(state_with({"history_events": empty})) == []


def test_relationship_timeline_merges_series_and_deduplicated_events():
    snapshots = pl.DataFrame(
        [
            {
                **snapshot("rel-1", "CAN|USA", 4, 25.0),
                "subject_type": "relationship",
                "indicator_id": "relationship.relation_value",
            }
        ]
    )
    event = {
        "id": "war-1",
        "subject_type": "country",
        "subject_id": "USA",
        "related_country_ids_json": '["USA", "CAN"]',
        "game_minute": 5,
        "tick": 1,
        "event_type": "WarEnded",
    }
    service = HistoryQueryService()
    timeline = service.relationship_timeline(
        state_with({"history_snapshots": snapshots, "history_events": pl.DataFrame([event])}),
        "usa",
        "can",
    )

    assert [row["timeline_kind"] for row in timeline] == ["relation_value", "event"]
    assert [row["id"] for row in timeline] == ["rel-1", "war-1"]


def test_cause_trail_limits_events_to_previous_day_and_keeps_causes():
    service = HistoryQueryService()
    service.event_timeline = Mock(return_value=[
        {"id": "cause", "cause_source_type": "policy"},
        {"id": "source", "source_type": "event"},
        {"id": "plain"},
    ])

    result = service.cause_trail(state_with(), "country", "USA", 600)

    service.event_timeline.assert_called_once_with(
        state_with(),
        subject_type="country",
        subject_id="USA",
        start_minute=0,
        end_minute=600,
    )
    assert [row["id"] for row in result] == ["cause", "source"]


def test_export_csv_handles_empty_rows_and_serializes_nested_values_deterministically():
    service = HistoryQueryService()
    assert service.export_csv([]) == ""

    exported = service.export_csv([
        {"subject_id": "USA", "details": {"z": 1, "a": 2}, "items": ["x", "y"]},
        {"subject_id": "CAN", "items": ("a", "b")},
    ])
    rows = list(csv.DictReader(io.StringIO(exported)))
    assert rows[0]["details"] == '{"a":2,"z":1}'
    assert rows[0]["items"] == '["x","y"]'
    assert rows[1]["items"] == '["a","b"]'


def test_history_query_small_helpers_normalize_and_reject_malformed_inputs():
    assert HistoryQueryService._bucket_last([], 5) == []
    assert HistoryQueryService._bucket_last(
        [{"id": "a", "game_minute": 1}, {"id": "b", "game_minute": 4}, {"id": "c", "game_minute": 5}],
        5,
    ) == [{"id": "b", "game_minute": 4}, {"id": "c", "game_minute": 5}]
    assert HistoryQueryService._pair_id(" can ", "usa") == "CAN|USA"
    assert HistoryQueryService._table(SimpleNamespace(), "missing") is None
    assert HistoryQueryService._json_ids('["usa", "", "can"]') == {"USA", "CAN"}
    assert HistoryQueryService._json_ids("invalid-json") == set()
    assert HistoryQueryService._json_ids({"not": "a collection"}) == set()
    assert HistoryQueryService._csv_value({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert HistoryQueryService._unavailable({"unit": "people"})["unit"] == "people"


def test_current_derived_values_cover_resource_treaty_war_and_party_policies():
    service = HistoryQueryService()
    assert service._current_derived_value(state_with(), "resource_coverage", "USA") is None
    assert service._current_derived_value(
        state_with({"resource_ledger": pl.DataFrame({"country_id": ["USA"]})}),
        "resource_coverage",
        "USA",
    ) is None
    assert service._current_derived_value(
        state_with({"resource_ledger": pl.DataFrame({"country_id": ["CAN"], "consumption_usd": [1.0], "balance_usd": [0.0]})}),
        "resource_coverage",
        "USA",
    ) is None
    assert service._current_derived_value(
        state_with({"resource_ledger": pl.DataFrame({"country_id": ["USA"], "consumption_usd": [0.0], "balance_usd": [0.0]})}),
        "resource_coverage",
        "USA",
    ) == 1.0
    assert service._current_derived_value(
        state_with({"resource_ledger": pl.DataFrame({"country_id": ["USA"], "consumption_usd": [2.0], "balance_usd": [-4.0]})}),
        "resource_coverage",
        "USA",
    ) == 0.0

    treaties = pl.DataFrame({
        "members": ['["USA", "CAN"]', "bad", '["USA"]'],
        "status": ["active", "active", "inactive"],
    })
    assert service._current_derived_value(
        state_with({"countries_treaties": treaties}), "treaty_membership_count", "usa"
    ) == 1.0
    assert service._current_derived_value(
        state_with({"countries_treaties": pl.DataFrame({"id": ["t1"]})}),
        "treaty_membership_count",
        "USA",
    ) is None

    wars = pl.DataFrame({
        "side_a": ['["USA"]', "USA", "MEX"],
        "side_b": ['["CAN"]', "[]", "CAN"],
        "status": ["active", "active", "ended"],
    })
    assert service._current_derived_value(state_with({"countries_wars": wars}), "active_war_count", "usa") == 2.0
    assert service._current_derived_value(
        state_with({"countries_wars": pl.DataFrame({"side_a": [[]]})}), "active_war_count", "USA"
    ) is None

    parties = pl.DataFrame({
        "country_id": ["USA", "USA"],
        "party_id": ["party-a", "party-b"],
        "support_share": [0.6, 0.4],
        "is_ruling": [False, True],
    })
    assert service._current_derived_value(state_with({"political_parties": parties}), "ruling_party_support", "usa") == 0.4
    government = pl.DataFrame({"country_id": ["USA"], "ruling_party_id": ["PARTY-A"]})
    assert service._current_derived_value(
        state_with({"political_parties": parties, "country_governments": government}),
        "ruling_party_support",
        "usa",
    ) == 0.6
    assert service._current_derived_value(
        state_with({
            "political_parties": parties,
            "country_governments": pl.DataFrame({"country_id": ["USA"], "ruling_party_id": ["missing"]}),
        }),
        "ruling_party_support",
        "USA",
    ) is None
    assert service._current_derived_value(
        state_with({"political_parties": pl.DataFrame({"id": ["x"]})}),
        "ruling_party_support",
        "USA",
    ) is None
    assert service._current_derived_value(state_with(), "unknown", "USA") is None


def test_current_value_routes_war_and_ruling_party_derivations():
    definitions = pl.DataFrame([
        definition("wars", derivation="active_war_count"),
        definition("support", derivation="ruling_party_support"),
    ])
    tables = {
        "history_indicator_definitions": definitions,
        "countries_wars": pl.DataFrame({"side_a": ['["USA"]'], "side_b": ["[]"], "status": ["active"]}),
        "political_parties": pl.DataFrame({"country_id": ["USA"], "party_id": ["A"], "support_share": [0.7], "is_ruling": [True]}),
    }
    service = HistoryQueryService()

    assert service.current_value(state_with(tables), "country", "USA", "wars")["value"] == 1.0
    assert service.current_value(state_with(tables), "country", "USA", "support")["value"] == 0.7
