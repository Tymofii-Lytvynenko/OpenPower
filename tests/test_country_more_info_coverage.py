from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

import src.client.ui.panels.country_more_info as country_info_module
from src.client.ui.panels.country_more_info import (
    CountryMoreInfoPanel,
    CountryMoreInfoPresenter,
)


def game_state(tables=None):
    return SimpleNamespace(globals={}, tables=tables or {})


def country_model():
    return CountryMoreInfoPresenter().build(
        game_state({
            "countries": pl.DataFrame({"id": ["USA"], "name": ["United States"], "human_dev": [0.8]}),
            "regions": pl.DataFrame({
                "id": [1], "owner": ["USA"], "controller": ["USA"], "area_km2": [50.0],
                "pop_14": [10], "pop_15_64": [80], "pop_65": [10],
            }),
        }),
        "USA",
    )


class FakeWidgets:
    def __init__(self, _path):
        self.pictures = []
        self.calls = []

    def picture(self, slot, draw):
        self.pictures.append((slot, draw))
        draw(200.0, 100.0)

    def text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))

    def meter(self, *args, **kwargs):
        self.calls.append(("meter", args, kwargs))

    def path(self, slot):
        return slot

    def rect(self, _slot):
        return None


def imgui_stub():
    draw_list = SimpleNamespace(add_rect_filled=Mock(), add_rect=Mock())
    point = SimpleNamespace(x=10.0, y=20.0)
    return SimpleNamespace(
        button=Mock(return_value=False),
        begin_child=Mock(return_value=True),
        end_child=Mock(),
        get_cursor_screen_pos=Mock(return_value=point),
        get_window_pos=Mock(return_value=SimpleNamespace(x=100.0, y=60.0)),
        get_window_draw_list=Mock(return_value=draw_list),
        get_color_u32=Mock(return_value=1),
        get_scroll_x=Mock(return_value=2.0),
        get_scroll_y=Mock(return_value=3.0),
        get_io=Mock(return_value=SimpleNamespace(display_size=SimpleNamespace(x=1000, y=800))),
        calc_text_size=Mock(return_value=SimpleNamespace(x=80.0, y=12.0)),
        set_cursor_screen_pos=Mock(),
        separator_text=Mock(),
        text_wrapped=Mock(),
        text_disabled=Mock(),
    )


def test_presenter_returns_safe_defaults_and_handles_region_schema_variants():
    presenter = CountryMoreInfoPresenter()

    empty = presenter.build(game_state(), " ")
    missing_authority = presenter.build(
        game_state({"regions": pl.DataFrame({"id": [1]})}), "USA"
    )
    owner_fallback = presenter.build(
        game_state({"regions": pl.DataFrame({"id": [1], "owner": ["USA"]})}), "USA"
    )
    invalid_filter = presenter.build(
        game_state({"regions": pl.DataFrame({"id": [1], "controller": [1]})}), "USA"
    )

    assert empty.region_ids == ()
    assert empty.region_summary == "No regional data loaded for this country."
    assert not empty.population_available and not empty.land_area_available
    assert missing_authority.region_ids == ()
    assert owner_fallback.region_ids == (1,)
    assert invalid_filter.region_ids == ()
    assert presenter._region_ids(pl.DataFrame({"name": ["no id"]})) == ()
    assert presenter._region_ids(pl.DataFrame({"id": [0, -1, None, 4]})) == (4,)


def test_presenter_builds_composition_without_area_weights_and_handles_bad_metadata():
    presenter = CountryMoreInfoPresenter()
    regions = pl.DataFrame({"macro_region": ["West", "East", "West"], "id": [1, 2, 3]})
    grouped = presenter._composition_rows(regions)

    assert [row.label for row in grouped] == ["West", "East"]
    assert [row.percent for row in grouped] == pytest.approx([200 / 3, 100 / 3])
    assert presenter._composition_rows(pl.DataFrame({"id": [1]})) == ()
    assert presenter._composition_rows(pl.DataFrame({"type": ["state"], "area_km2": [0.0]}))[0].percent == 0.0
    assert presenter._region_summary(pl.DataFrame({"name": ["no supported metadata"]})) == "Regional metadata is not available."
    assert presenter._region_summary(pl.DataFrame({"biome": [None, "Forest", "Desert", "Forest"]})) == "Desert, Forest"


def test_presenter_filters_and_formats_production_rows_and_handles_missing_columns():
    presenter = CountryMoreInfoPresenter()
    assert presenter._production_rows(game_state(), "USA") == ()
    assert presenter._production_rows(
        game_state({"domestic_production": pl.DataFrame({"country_id": ["USA"]})}), "USA"
    ) == ()

    rows = presenter._production_rows(
        game_state({"domestic_production": pl.DataFrame({
            "country_id": ["USA", "USA"],
            "game_resource_id": ["oil", "food"],
            "domestic_production": [0.0, 0.0],
        })}),
        "USA",
    )

    assert {row.label for row in rows} == {"Food", "Oil"}
    assert all(row.percent == 0.0 for row in rows)
    assert [presenter._format_money(value) for value in (500, 1_000_000, 1_000_000_000, 1_000_000_000_000)] == [
        "$ 500", "$ 1.0M", "$ 1.0B", "$ 1.0T",
    ]
    assert presenter._sum_column(None, "area_km2") == 0.0
    assert presenter._sum_column(pl.DataFrame({"x": [1]}), "area_km2") == 0.0


def test_presenter_ignores_tables_that_fail_during_polars_operations():
    class BrokenTable:
        def __init__(self, columns):
            self.columns = columns

        def is_empty(self):
            return False

        def group_by(self, *_args, **_kwargs):
            raise RuntimeError("invalid grouped table")

        def filter(self, *_args, **_kwargs):
            raise RuntimeError("invalid production table")

        def select(self, *_args, **_kwargs):
            raise RuntimeError("invalid numeric table")

    presenter = CountryMoreInfoPresenter()

    assert presenter._composition_rows(BrokenTable(["type"])) == ()
    assert presenter._production_rows(
        game_state({"domestic_production": BrokenTable(["country_id", "game_resource_id", "domestic_production"])}),
        "USA",
    ) == ()
    assert presenter._sum_column(BrokenTable(["area_km2"]), "area_km2") == 0.0


def test_panel_content_draws_country_sections_and_map_placeholder(monkeypatch):
    imgui = imgui_stub()
    monkeypatch.setattr(country_info_module, "imgui", imgui)
    monkeypatch.setattr(country_info_module, "GMLWidgets", FakeWidgets)
    separators = Mock()
    monkeypatch.setattr(country_info_module, "draw_gml_separator", separators)
    monkeypatch.setattr(country_info_module, "active_gml_layout", lambda: None)
    panel = CountryMoreInfoPanel()
    panel._map_textures = Mock()
    panel._map_textures.get_texture.return_value = None

    panel._render_content(country_model())

    assert separators.call_count == 2
    imgui.text_disabled.assert_called_once_with("No region map")
    assert imgui.get_window_draw_list.return_value.add_rect.call_count == 1


def test_panel_draws_source_frame_and_fitted_map_texture(monkeypatch):
    imgui = imgui_stub()
    monkeypatch.setattr(country_info_module, "imgui", imgui)
    monkeypatch.setattr(
        country_info_module,
        "active_gml_layout",
        lambda: SimpleNamespace(window_position=(100.0, 200.0)),
    )
    panel = CountryMoreInfoPanel()
    ui = SimpleNamespace(rect=Mock(return_value=SimpleNamespace(x=5.0, y=7.0, width=40.0, height=30.0)))

    panel._draw_source_frame(ui, "frmLand")

    imgui.get_window_draw_list.return_value.add_rect_filled.assert_called_once()
    imgui.get_window_draw_list.return_value.add_rect.assert_called_once()
    assert panel._fit_texture(SimpleNamespace(width=100, height=50), 100.0, 80.0) == (100.0, 50.0)
    assert panel._fit_texture(SimpleNamespace(width=0, height=50), 100.0, 80.0) == (100.0, 80.0)

    texture = SimpleNamespace(width=100, height=50)
    panel._map_data_provider = lambda: object()
    panel._map_textures = Mock()
    panel._map_textures.get_texture.return_value = texture
    panel._draw_region_map(country_model(), 120.0, 80.0)

    panel._map_textures.get_texture.assert_called_once()
    panel._map_textures.draw_texture.assert_called_once_with(texture, 106.0, 53.0, test_id="country.info.region_map")
    assert imgui.set_cursor_screen_pos.call_count == 2


def test_render_respects_window_state_and_centers_to_viewport(monkeypatch):
    imgui = imgui_stub()
    monkeypatch.setattr(country_info_module, "imgui", imgui)
    monkeypatch.setattr(country_info_module, "get_gml_layout", lambda _name: SimpleNamespace(width=600, height=500))
    opened = False
    positions = []

    @contextmanager
    def window(title, **bounds):
        positions.append((title, bounds))
        yield opened

    monkeypatch.setattr(country_info_module.WindowManager, "window", window)
    panel = CountryMoreInfoPanel()
    panel._presenter.build = Mock(return_value=country_model())
    panel._render_content = Mock()
    context = SimpleNamespace(target_tag="USA")

    assert panel.render(game_state(), context) is False
    opened = True
    assert panel.render(game_state(), context) is True

    assert positions[-1][1]["x"] == 200.0
    assert positions[-1][1]["y"] == 60.0
    panel._render_content.assert_called_once()


def test_party_roster_presenter_keeps_source_records_and_notes_separate():
    state = game_state(
        {
            "countries": pl.DataFrame({"id": ["USA"], "name": ["United States"]}),
            "country_party_roster_2001": pl.DataFrame(
                [{
                    "country_id": "USA",
                    "display_name": "Example Party",
                    "leaders_text": "Example Leader",
                    "leader_status": "reported",
                    "source_entry": "Example Party [Example Leader]",
                    "source_notes": "note - source context",
                    "source_country": "United States",
                    "source_reference": "Factbook 2001, United States, Political parties and leaders",
                    "source_url": "https://www.gutenberg.org/cache/epub/27638/pg27638.txt",
                    "source_note": "No comparable vote or support share is reported.",
                }]
            ),
            "country_party_roster_coverage_2001": pl.DataFrame(
                [{
                    "country_id": "USA",
                    "source_country": "United States",
                    "status": "reported",
                    "party_record_count": 1,
                    "source_reference": "Factbook 2001, United States, Political parties and leaders",
                    "source_url": "https://www.gutenberg.org/cache/epub/27638/pg27638.txt",
                    "source_note": "No comparable vote or support share is reported.",
                }]
            ),
        }
    )

    context = CountryMoreInfoPresenter().build(state, "USA").party_roster_2001

    assert context.status == "reported"
    assert context.source_country == "United States"
    assert context.entries[0].source_entry == "Example Party [Example Leader]"
    assert context.entries[0].leaders_text == "Example Leader"
    assert context.source_notes == ("note - source context",)
    assert "No comparable vote" in context.source_note


def test_country_info_roster_dialog_shows_all_seven_explicit_coverage_statuses(monkeypatch):
    missing = {
        "ATA": ("party_field_not_reported", "Antarctica"),
        "KOS": ("no_separate_country_entry", ""),
        "MNE": ("no_separate_country_entry", ""),
        "PSE": ("party_field_not_reported", "West Bank"),
        "SRB": ("no_separate_country_entry", ""),
        "SSD": ("no_separate_country_entry", ""),
        "TLS": ("no_separate_country_entry", ""),
    }
    coverage = pl.DataFrame(
        [
            {
                "country_id": country_id,
                "source_country": source_country,
                "status": status,
                "party_record_count": 0,
                "source_reference": "CIA World Factbook 2001",
                "source_url": "https://www.gutenberg.org/cache/epub/27638/pg27638.txt",
                "source_note": "No field-specific estimate year or party shares are reported.",
            }
            for country_id, (status, source_country) in missing.items()
        ]
    )
    state = game_state({"country_party_roster_coverage_2001": coverage})
    fake_imgui = imgui_stub()
    monkeypatch.setattr(country_info_module, "imgui", fake_imgui)
    panel = CountryMoreInfoPanel()

    for country_id, (status, _source_country) in missing.items():
        fake_imgui.text_wrapped.reset_mock()
        fake_imgui.text_disabled.reset_mock()
        model = CountryMoreInfoPresenter().build(state, country_id)
        panel._render_party_roster_content(model)

        status_labels = [call.args[0] for call in fake_imgui.text_disabled.call_args_list]
        reasons = [call.args[0] for call in fake_imgui.text_wrapped.call_args_list]
        assert f"Source status: {status}" in status_labels
        assert any(country_id in reason for reason in reasons)
        if status == "no_separate_country_entry":
            assert any("no separate country entry" in reason for reason in reasons)
        else:
            assert any("does not report the Political parties and leaders field" in reason for reason in reasons)


def test_country_info_button_opens_a_scrollable_factbook_roster_child_dialog(monkeypatch):
    state = game_state(
        {
            "countries": pl.DataFrame({"id": ["USA"], "name": ["United States"]}),
            "country_party_roster_2001": pl.DataFrame(
                [{
                    "country_id": "USA",
                    "display_name": "Example Party",
                    "leaders_text": "Example Leader",
                    "leader_status": "reported",
                    "source_entry": "Example Party [Example Leader]",
                    "source_notes": "note - source context",
                    "source_country": "United States",
                    "source_reference": "Factbook 2001, United States, Political parties and leaders",
                    "source_url": "https://www.gutenberg.org/cache/epub/27638/pg27638.txt",
                    "source_note": "No comparable vote or support share is reported.",
                }]
            ),
            "country_party_roster_coverage_2001": pl.DataFrame(
                [{
                    "country_id": "USA",
                    "source_country": "United States",
                    "status": "reported",
                    "party_record_count": 1,
                    "source_reference": "Factbook 2001, United States, Political parties and leaders",
                    "source_url": "https://www.gutenberg.org/cache/epub/27638/pg27638.txt",
                    "source_note": "No comparable vote or support share is reported.",
                }]
            ),
        }
    )
    fake_imgui = imgui_stub()
    fake_imgui.button.side_effect = [True, False]
    monkeypatch.setattr(country_info_module, "imgui", fake_imgui)
    monkeypatch.setattr(
        country_info_module,
        "get_gml_layout",
        lambda _name: SimpleNamespace(width=519, height=431),
    )
    windows = []

    @contextmanager
    def window(title, **kwargs):
        windows.append((title, kwargs))
        yield True

    monkeypatch.setattr(country_info_module.WindowManager, "window", window)
    panel = CountryMoreInfoPanel()
    panel._render_content = Mock()

    assert panel.render(state, SimpleNamespace(target_tag="USA"))

    assert len(windows) == 2
    assert windows[1][1]["test_id"] == "country.info.party_roster.dialog"
    assert windows[1][1]["closable"] is True
    fake_imgui.begin_child.assert_called_once()
    assert fake_imgui.begin_child.call_args.kwargs["test_id"] == "country.info.party_roster.list"
    rendered_text = [call.args[0] for call in fake_imgui.text_wrapped.call_args_list]
    assert "Example Party [Example Leader]" in rendered_text
    assert "Leaders: Example Leader" in rendered_text
    assert "note - source context" in rendered_text
    assert not any("political_parties" in str(call) for call in fake_imgui.button.call_args_list)


def test_country_info_election_results_keep_reported_metrics_and_missing_values_separate(
    monkeypatch,
):
    table = pl.DataFrame(
        [
            {
                "event_id": "KOS_2001_assembly",
                "country_id": "KOS",
                "election_date": "2001-11-17",
                "additional_election_date": "",
                "geography": "Kosovo (UN-administered territory)",
                "result_label": "PGJK — Green Party of Kosovo",
                "votes": 2325,
                "vote_share_pct": 0.29,
                "seats": 0,
                "general_seats": None,
                "special_seats": None,
                "result_scope": "All 26 political entities; 120 Assembly seats.",
                "source_name": "OSCE / Kosovo Central Election Commission",
                "source_reference": "Certified Election 2001 results, page 1.",
                "source_url": "https://example.org/kosovo-results.pdf",
                "source_note": "Election held 17 November 2001.",
            },
            {
                "event_id": "TLS_2001_assembly",
                "country_id": "TLS",
                "election_date": "2001-08-30",
                "additional_election_date": "",
                "geography": "East Timor",
                "result_label": "FRETILIN",
                "votes": None,
                "vote_share_pct": 57.37,
                "seats": 55,
                "general_seats": 55,
                "special_seats": 0,
                "result_scope": "National-list ballot; 75 proportional seats.",
                "source_name": "UNTAET Independent Electoral Commission",
                "source_reference": "Final results announcement.",
                "source_url": "https://example.org/timor-results.html",
                "source_note": "Party raw vote counts were not published.",
            },
        ]
    )
    state = game_state({"country_election_results": table})

    kosovo = CountryMoreInfoPresenter().build(state, "KOS")
    timor = CountryMoreInfoPresenter().build(state, "TLS")

    assert len(kosovo.election_results_2001) == 1
    assert len(kosovo.election_results_2001[0].results) == 1
    assert kosovo.election_results_2001[0].results[0].votes == 2325
    assert kosovo.election_results_2001[0].results[0].seats == 0
    assert timor.election_results_2001[0].results[0].votes is None

    fake_imgui = imgui_stub()
    monkeypatch.setattr(country_info_module, "imgui", fake_imgui)
    CountryMoreInfoPanel._render_election_results(timor.election_results_2001)

    rendered_text = [call.args[0] for call in fake_imgui.text_wrapped.call_args_list]
    assert "FRETILIN — 57.37%, 55 seats (55 general, 0 special)" in rendered_text
    assert "Party raw vote counts were not published." in rendered_text
    assert not any("0 votes" in text for text in rendered_text)
