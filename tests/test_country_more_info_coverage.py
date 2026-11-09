from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

import src.client.ui.panels.country_more_info as country_info_module
from src.client.ui.panels.country_more_info import CountryMoreInfoPanel, CountryMoreInfoPresenter


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
        get_cursor_screen_pos=Mock(return_value=point),
        get_window_draw_list=Mock(return_value=draw_list),
        get_color_u32=Mock(return_value=1),
        get_scroll_x=Mock(return_value=2.0),
        get_scroll_y=Mock(return_value=3.0),
        calc_text_size=Mock(return_value=SimpleNamespace(x=80.0, y=12.0)),
        set_cursor_screen_pos=Mock(),
        text_disabled=Mock(),
        get_io=Mock(return_value=SimpleNamespace(display_size=SimpleNamespace(x=1000, y=800))),
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
