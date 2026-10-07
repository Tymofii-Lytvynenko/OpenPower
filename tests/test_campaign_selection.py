from __future__ import annotations

import polars as pl

from src.client.services.campaign_selection import (
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
