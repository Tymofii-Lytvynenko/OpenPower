from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

from src.client.ui.panels.shared import panel_data


def _state(*, tables=None, globals=None):
    return SimpleNamespace(tables=tables or {}, globals=globals)


def test_country_row_lookup_handles_empty_catalogs_and_unknown_tags():
    assert panel_data.get_country_row(_state(), "AAA") == {}
    assert panel_data.get_country_row(_state(tables={"countries": pl.DataFrame()}), "AAA") == {}
    assert panel_data.get_country_row(
        _state(tables={"countries": pl.DataFrame({"name": ["Alpha"]})}),
        "AAA",
    ) == {}

    countries = pl.DataFrame({"id": ["AAA"], "name": ["Alpha"]})
    assert panel_data.get_country_row(_state(tables={"countries": countries}), "ZZZ") == {}
    assert panel_data.get_country_row(_state(tables={"countries": countries}), "AAA") == {
        "id": "AAA",
        "name": "Alpha",
    }


def test_active_country_catalog_normalizes_tags_and_respects_boolean_and_text_flags():
    for state in (
        _state(),
        _state(tables={"countries": pl.DataFrame()}),
        _state(tables={"countries": pl.DataFrame({"name": ["Alpha"]})}),
    ):
        assert panel_data.active_country_tags(state) == []

    boolean_countries = pl.DataFrame(
        {"id": ["z", "a", "inactive", " "], "active": [True, True, False, True]}
    )
    assert panel_data.active_country_tags(_state(tables={"countries": boolean_countries})) == ["A", "Z"]

    for inactive in ("false", "0", "no", "inactive"):
        text_countries = pl.DataFrame({"id": ["kept", "hidden"], "active": ["yes", inactive]})
        assert panel_data.active_country_tags(_state(tables={"countries": text_countries})) == ["KEPT"]

    countries_without_active_column = pl.DataFrame({"id": ["usa"]})
    assert panel_data.active_country_tags(
        _state(tables={"countries": countries_without_active_column})
    ) == ["USA"]


def test_country_and_region_name_fallbacks_use_catalog_values_and_stable_labels(monkeypatch):
    resolver = SimpleNamespace(
        country_name=Mock(return_value=None),
        region_name=Mock(return_value=None),
    )
    monkeypatch.setattr(panel_data, "get_geo_name_resolver", lambda _language: resolver)

    assert panel_data.resolve_country_name(_state(), "  zzz ") == "zzz"
    countries = pl.DataFrame({"id": ["AAA"], "name": ["Alpha"]})
    state = _state(tables={"countries": countries}, globals={"geo_language_code": "uk"})
    assert panel_data.resolve_country_name(state, "AAA") == "Alpha"
    assert panel_data.resolve_country_name(state, "ZZZ") == "ZZZ"
    assert panel_data.resolve_country_name(
        _state(tables={"countries": pl.DataFrame({"id": ["AAA"]})}),
        "AAA",
    ) == "AAA"

    assert panel_data.resolve_region_name(state, 0) == "Unknown"
    assert panel_data.resolve_region_name(_state(), 7) == "Region 7"
    assert panel_data.resolve_region_name(
        _state(tables={"regions": pl.DataFrame({"id": [1]})}),
        7,
    ) == "Region 7"
    region_without_display_name = pl.DataFrame({"id": [7], "iso_region": ["ZZ-UNKNOWN"]})
    assert panel_data.resolve_region_name(
        _state(tables={"regions": region_without_display_name}),
        7,
    ) == "Region 7"


def test_side_and_playable_helpers_accept_supported_shapes_and_reject_others(monkeypatch):
    assert panel_data.normalize_side(None) == ()
    assert panel_data.normalize_side(["AAA", None]) == ("AAA",)
    assert panel_data.normalize_side(("AAA", None)) == ("AAA",)
    assert panel_data.normalize_side(" AAA, BBB ,, ") == ("AAA", "BBB")
    assert panel_data.normalize_side(42) == ()

    resolver = SimpleNamespace(country_name=lambda tag: {"AAA": "Alpha", "BBB": "Beta"}.get(tag))
    monkeypatch.setattr(panel_data, "get_geo_name_resolver", lambda _language: resolver)
    assert panel_data.format_side_names(_state(), ["AAA", "BBB"]) == "Alpha, Beta"
    assert panel_data.format_side_names(_state(), None) == "None"

    assert panel_data.is_playable_country({"is_playable": True}) is True
    assert panel_data.is_playable_country({"is_playable": False}) is False
    assert panel_data.is_playable_country({"is_playable": "TRUE"}) is True
    assert panel_data.is_playable_country({"is_playable": "yes"}) is False
    assert panel_data.is_playable_country({}) is True


def test_row_and_member_helpers_handle_empty_and_string_inputs():
    assert panel_data.safe_float("not numeric", 2.5) == 2.5
    assert panel_data.safe_int("not an integer", 4) == 4
    assert panel_data.as_ratio(25) == 0.25

    assert panel_data.top_rows(None) == []
    assert panel_data.top_rows(pl.DataFrame()) == []
    rows = pl.DataFrame({"id": [1, 2], "name": ["one", "two"]})
    assert panel_data.top_rows(rows, count=1) == [{"id": 1, "name": "one"}]

    assert panel_data.format_members_count(["AAA", None, "BBB"]) == 2
    assert panel_data.format_members_count("AAA, ,BBB") == 2
    assert panel_data.format_members_count(42) == 0
