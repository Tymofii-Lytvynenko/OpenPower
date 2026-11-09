from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.components.hud.thematic_map_legend as legend_module
from src.client.ui.components.hud.thematic_map_legend import LegendCountry, ThematicMapLegend


def _table(rows, columns):
    return SimpleNamespace(
        columns=columns,
        is_empty=Mock(return_value=not rows),
        to_dicts=Mock(return_value=rows),
    )


def _imgui_mock(monkeypatch):
    imgui = Mock()
    imgui.Col_.window_bg = 1
    imgui.WindowFlags_.no_title_bar = 1
    imgui.WindowFlags_.no_move = 2
    imgui.WindowFlags_.no_resize = 4
    imgui.WindowFlags_.no_collapse = 8
    imgui.WindowFlags_.no_scrollbar = 16
    imgui.WindowFlags_.no_scroll_with_mouse = 32
    imgui.get_cursor_screen_pos.return_value = SimpleNamespace(x=10.0, y=20.0)
    imgui.get_mouse_pos.return_value = SimpleNamespace(x=11.0, y=21.0)
    monkeypatch.setattr(legend_module, "imgui", imgui)
    return imgui


def test_country_helpers_normalize_activity_relations_names_and_colors():
    viewport = SimpleNamespace(
        selected_country_tag=None,
        map_modes={"empire": SimpleNamespace(selected_country=" pol ")},
    )
    legend = ThematicMapLegend(viewport)

    assert legend._selected_country_tag() == "POL"
    assert legend._normalize_tag(None) == ""
    assert legend._normalize_tag(" none ") == ""
    assert legend._normalize_tag(" ukr ") == "UKR"
    assert legend._is_active({"is_active": False, "status": "active"}) is False
    assert legend._is_active({"active": True, "status": "dead"}) is True
    assert legend._is_active({"status": " ELIMINATED "}) is False
    assert legend._is_active({"status": "active"}) is True
    assert legend._finite_float("3.5") == 3.5
    assert legend._finite_float("bad") is None
    assert legend._finite_float(float("inf")) is None

    countries = _table(
        [{"id": "ukr", "country_name": "Ukraine"}, {"id": "pol", "country_name": None}],
        ["id", "country_name"],
    )
    assert legend._country_names(countries) == {"UKR": "Ukraine", "POL": "pol"}
    id_only = _table([{"id": "usa"}], ["id"])
    assert legend._country_names(id_only) == {"USA": "usa"}

    relations = _table([
        {"source": "UKR", "target": "POL", "value": "42"},
        {"source": "ukr", "target": "USA", "value": "nan"},
        {"source": "POL", "target": "UKR", "value": 9},
    ], ["source", "target", "value"])
    state = SimpleNamespace(tables={"countries_relations": relations})
    assert legend._relation_values(state, " ukr ") == {"POL": 42.0}
    assert legend._relation_values(state, "") == {}
    assert legend._relation_values(SimpleNamespace(tables={}), "UKR") == {}
    assert legend._relation_values(
        SimpleNamespace(tables={"countries_relations": _table([], ["source"])}), "UKR",
    ) == {}

    positive = legend._relation_color(100)
    negative = legend._relation_color(-100)
    assert positive[1] > positive[0]
    assert negative[0] > negative[1]


def test_country_metric_values_aggregate_regions_and_fall_back_to_country_data():
    mode = SimpleNamespace(column_name="gdp")
    regions = _table([
        {"owner": " ukr ", "gdp": 100.0},
        {"owner": "UKR", "gdp": 300.0},
        {"owner": "POL", "gdp": "invalid"},
        {"owner": "", "gdp": 500.0},
    ], ["owner", "gdp"])
    state = SimpleNamespace(tables={"regions": regions})
    assert ThematicMapLegend._country_metric_values(state, mode) == {"UKR": 200.0}

    countries = _table([
        {"id": "usa", "gdp": 500.0},
        {"id": "", "gdp": 400.0},
        {"id": "can", "gdp": "bad"},
    ], ["id", "gdp"])
    fallback = SimpleNamespace(tables={"countries": countries, "regions": _table([], ["owner"])})
    assert ThematicMapLegend._country_metric_values(fallback, mode) == {
        "USA": 500.0, "CAN": None,
    }
    assert ThematicMapLegend._country_metric_values(
        SimpleNamespace(tables={}), SimpleNamespace(column_name=""),
    ) == {}
    assert ThematicMapLegend._country_metric_values(
        SimpleNamespace(tables={}), mode,
    ) == {}


def test_ranked_countries_returns_only_active_rows_with_finite_values():
    legend = ThematicMapLegend(SimpleNamespace(selected_country_tag="active", map_modes={}))
    countries = _table([
        {"id": "inactive", "display_name": "Inactive", "gdp": 99, "status": "eliminated"},
        {"id": " ", "display_name": "No id", "gdp": 100, "status": "active"},
        {"id": "invalid", "display_name": "Invalid", "gdp": "bad", "status": "active"},
        {"id": "active", "display_name": "Active", "gdp": 10, "is_active": True},
    ], ["id", "display_name", "gdp", "status", "is_active"])
    state = SimpleNamespace(tables={"countries": countries})

    rows = legend._ranked_countries(state, "USA", "ACTIVE", SimpleNamespace(column_name="gdp"))
    assert rows == [LegendCountry("ACTIVE", "Active", None, True)]
    assert legend._ranked_countries(SimpleNamespace(tables={}), "USA", "", SimpleNamespace(column_name="gdp")) == []
    assert legend._ranked_countries(
        SimpleNamespace(tables={"countries": _table([], ["id"])}),
        "USA", "", SimpleNamespace(column_name="gdp"),
    ) == []
    assert legend._ranked_countries(
        SimpleNamespace(tables={"countries": _table([], ["name"])}),
        "USA", "", SimpleNamespace(column_name="gdp"),
    ) == []
    assert legend._ranked_countries(
        SimpleNamespace(tables={"countries": _table([{"id": "UKR", "gdp": None}], ["id", "gdp"])}),
        "USA", "", SimpleNamespace(column_name="gdp"),
    ) == []


def test_empire_country_list_rejects_missing_selection_or_country_data(monkeypatch):
    legend = ThematicMapLegend(SimpleNamespace(selected_country_tag=None, map_modes={}))
    assert legend._empire_countries(SimpleNamespace(tables={}), "UKR", "UKR") == []
    assert legend._empire_countries(
        SimpleNamespace(tables={"countries": _table([], ["id"])}), "UKR", "UKR",
    ) == []
    assert legend._empire_countries(
        SimpleNamespace(tables={"countries": _table([], ["name"])}), "UKR", "UKR",
    ) == []
    assert legend._empire_countries(
        SimpleNamespace(tables={"countries": _table([], ["id"])}), "", "UKR",
    ) == []

    viewport = SimpleNamespace(selected_country_tag=" CAN ", map_modes={})
    legend = ThematicMapLegend(viewport)
    assert legend._selected_country_tag() == "CAN"


def test_render_skips_default_modes_and_always_restores_style(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    missing_mode = ThematicMapLegend(SimpleNamespace(map_modes={}))
    missing_mode.render(SimpleNamespace(), "UKR")
    political = ThematicMapLegend(SimpleNamespace(
        current_mode_key="political", map_modes={"political": object()},
    ))
    political.render(SimpleNamespace(), "UKR")
    assert imgui.push_style_color.call_count == 0

    opened = {"value": True}

    @contextmanager
    def window_context(*_args, **_kwargs):
        yield opened["value"]

    monkeypatch.setattr(legend_module.WindowManager, "window", window_context)
    viewport = SimpleNamespace(current_mode_key="gdp", map_modes={"gdp": SimpleNamespace(steps=2)})
    legend = ThematicMapLegend(viewport)
    legend._render_content = Mock()
    legend.render(SimpleNamespace(), "UKR")
    opened["value"] = False
    legend.render(SimpleNamespace(), "UKR")

    assert legend._render_content.call_count == 1
    assert imgui.push_style_color.call_count == 2
    assert imgui.pop_style_color.call_count == 2


def test_render_content_routes_modes_empty_rows_and_country_rows(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    ui = Mock()
    monkeypatch.setattr(legend_module, "GMLWidgets", Mock(return_value=ui))
    child_state = {"open": True}

    @contextmanager
    def child_frame(*_args, **_kwargs):
        yield child_state["open"]

    row_ui = Mock()

    @contextmanager
    def row_frame(*_args, **_kwargs):
        yield row_ui

    monkeypatch.setattr(legend_module, "gml_child_frame", child_frame)
    monkeypatch.setattr(legend_module, "gml_row", row_frame)
    legend = ThematicMapLegend(SimpleNamespace(selected_country_tag="UKR", map_modes={}))
    row = LegendCountry("UKR", "Ukraine", None, True)
    legend._draw_gradient_key = Mock()
    legend._draw_empire_key = Mock()
    legend._ranked_countries = Mock(side_effect=[[], [row], [row]])
    legend._empire_countries = Mock(return_value=[])
    legend._render_country_row = Mock()

    legend._render_content(SimpleNamespace(), "UKR", "gdp", SimpleNamespace(name="GDP"))
    legend._render_content(SimpleNamespace(), "UKR", "empire", object())
    child_state["open"] = False
    legend._render_content(SimpleNamespace(), "UKR", "gdp", object())
    child_state["open"] = True
    legend._render_content(SimpleNamespace(), "UKR", "gdp", object())

    assert ui.text_at.call_args_list[0].args[:2] == ("lstCountries", "No country data")
    assert ui.text_at.call_args_list[1].args[:2] == ("lstCountries", "Select a country")
    legend._draw_empire_key.assert_called_once_with(ui)
    assert legend._render_country_row.call_count == 1
    legend._render_country_row.assert_called_once_with(row_ui, row, 1)
    assert imgui.begin_child.call_count == 0


def test_render_country_rows_handles_selection_hover_relations_and_flag_fallback(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    imgui.invisible_button.side_effect = [True, False, True]
    imgui.is_item_hovered.side_effect = [True, False, False]
    draw_list = imgui.get_window_draw_list.return_value
    viewport = SimpleNamespace(focus_on_country=Mock())
    legend = ThematicMapLegend(viewport)
    ui = Mock()

    legend._render_country_row(ui, LegendCountry("UKR", "Ukraine", 42.0, False), 1)
    legend._render_country_row(ui, LegendCountry("POL", "Poland", None, True), 2)
    legend._draw_flag("USA", 8.0, 6.0)

    viewport.focus_on_country.assert_called_once_with("UKR")
    assert ui.text.call_count == 5
    assert ui.text.call_args_list[2].args[:2] == ("frmCountry/lblRelations", "42")
    assert imgui.set_tooltip.call_count == 1
    assert draw_list.add_rect_filled.call_count == 3

    renderer = Mock()
    ThematicMapLegend(viewport, flag_renderer=renderer)._draw_flag("CAN", 8.0, 6.0)
    renderer.draw_flag.assert_called_once_with("CAN", 8.0, 6.0)

    no_focus = ThematicMapLegend(SimpleNamespace())
    no_focus._render_country_row(ui, LegendCountry("CAN", "Canada", None, False), 3)


def test_gradient_and_empire_keys_draw_their_color_entries(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    draw_list = imgui.get_window_draw_list.return_value
    monkeypatch.setattr(legend_module, "get_heatmap_color", lambda value: (int(value * 255), 10, 20))
    ui = Mock()
    ui.picture.side_effect = lambda _slot, draw: draw(8.0, 32.0)

    ThematicMapLegend._draw_gradient_key(ui, SimpleNamespace(steps=3))
    assert draw_list.add_rect_filled.call_count == 4
    assert draw_list.add_rect.call_count == 1
    assert ui.text.call_count == 2

    draw_list.reset_mock()
    ThematicMapLegend._draw_gradient_key(ui, SimpleNamespace(steps=1))
    assert draw_list.add_rect_filled.call_count == 32

    ui.rect.return_value = SimpleNamespace(x=4.0, y=6.0, width=10.0, height=50.0)
    monkeypatch.setattr(
        legend_module,
        "active_gml_layout",
        lambda: SimpleNamespace(window_position=(100.0, 200.0)),
    )
    draw_list.reset_mock()
    ThematicMapLegend._draw_empire_key(ui)
    assert draw_list.add_rect_filled.call_count == 5
    assert ui.text_at.call_count == 5
    assert draw_list.add_rect.call_count == 1
