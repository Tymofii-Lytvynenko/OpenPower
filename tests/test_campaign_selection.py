from __future__ import annotations

import polars as pl
import pytest

from src.client.services.campaign_selection import (
    filter_playable_countries,
    filter_selectable_countries,
    preview_campaign_scenario,
)


def test_scenario_allowlist_filters_playable_country_choices_case_insensitively() -> None:
    playable = pl.DataFrame({"id": ["CAN", "USA", "MEX"], "is_playable": [True, True, True]})
    scenario = {"selectable_country_ids_json": '["usa", "MEX"]'}

    eligible = filter_selectable_countries(playable, scenario)

    assert eligible["id"].to_list() == ["USA", "MEX"]


def test_invalid_scenario_allowlist_fails_closed_and_empty_allowlist_preserves_sandbox() -> None:
    playable = pl.DataFrame({"id": ["CAN", "USA"]})

    assert filter_selectable_countries(playable, {"selectable_country_ids_json": "{"}).is_empty()
    assert filter_selectable_countries(playable, {"selectable_country_ids_json": "[]"}).equals(playable)


def test_playable_country_filter_uses_runtime_default_when_metadata_is_missing() -> None:
    countries = pl.DataFrame({"id": ["ATA", "UKR"]})

    assert filter_playable_countries(countries).equals(countries)


def test_playable_country_filter_excludes_explicit_false_and_keeps_null_defaults() -> None:
    countries = pl.DataFrame({
        "id": ["ATA", "UKR", "USA"],
        "is_playable": ["false", "true", None],
    })

    assert filter_playable_countries(countries)["id"].to_list() == ["UKR", "USA"]


def test_scenario_preview_exposes_scope_rules_objectives_and_deadlines() -> None:
    preview = preview_campaign_scenario({
        "political_scope": "sphere",
        "sphere_scope": "trade_union",
        "enabled_rules_json": '{"combat": true, "migration": false}',
        "objectives_json": '[{"title":"Join the treaty","deadline_minutes":90}]',
        "max_duration_minutes": 300,
    })

    assert preview.scope == "Sphere: trade_union"
    assert preview.enabled_rules == ("combat",)
    assert [(item.title, item.deadline) for item in preview.objectives] == [
        ("Join the treaty", "within 90 minute(s)")
    ]
    assert preview.max_duration_minutes == 300


def test_selectable_country_filter_preserves_input_without_scenario_or_ids() -> None:
    empty = pl.DataFrame(schema={"id": pl.String})
    without_ids = pl.DataFrame({"name": ["USA"]})
    playable = pl.DataFrame({"id": ["USA"]})

    assert filter_selectable_countries(empty, {}) is empty
    assert filter_selectable_countries(without_ids, {}) is without_ids
    assert filter_selectable_countries(playable, None) is playable


def test_selectable_country_filter_handles_non_list_and_blank_allowlists() -> None:
    playable = pl.DataFrame({"id": ["USA"]})

    assert filter_selectable_countries(
        playable,
        {"selectable_country_ids_json": "{}"},
    ).is_empty()
    assert filter_selectable_countries(
        playable,
        {"selectable_country_ids_json": '[" ", ""]'},
    ).is_empty()


@pytest.mark.parametrize(
    "countries",
    [
        pl.DataFrame(schema={"id": pl.String, "is_playable": pl.Boolean}),
        pl.DataFrame({"name": ["USA"], "is_playable": [False]}),
    ],
)
def test_playable_country_filter_preserves_empty_or_idless_input(
    countries: pl.DataFrame,
) -> None:
    assert filter_playable_countries(countries) is countries


def test_scenario_preview_defaults_when_scenario_is_missing_or_has_bad_object_json() -> None:
    assert preview_campaign_scenario(None).scope == "Country"

    preview = preview_campaign_scenario(
        {
            "enabled_rules_json": "[]",
            "objectives_json": "[]",
            "max_duration_minutes": "not-a-number",
        }
    )

    assert preview.enabled_rules == ()
    assert preview.objectives == ()
    assert preview.max_duration_minutes == 0


def test_scenario_preview_defaults_when_objectives_json_is_not_a_list() -> None:
    preview = preview_campaign_scenario(
        {"enabled_rules_json": "{}", "objectives_json": "{}"}
    )

    assert preview.objectives == ()


def test_scenario_preview_formats_absolute_and_invalid_deadlines() -> None:
    preview = preview_campaign_scenario(
        {
            "objectives_json": (
                '[{"id":"absolute","deadline_at_minute":42},'
                '{"id":"invalid","deadline_at_minute":"bad",'
                '"deadline_minutes":"bad"},{"id":"none"},"ignored"]'
            )
        }
    )

    assert [(item.title, item.deadline) for item in preview.objectives] == [
        ("absolute", "game minute 42"),
        ("invalid", "within 0 minute(s)"),
        ("none", "no deadline"),
    ]
