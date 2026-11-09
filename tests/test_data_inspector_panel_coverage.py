from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

import src.client.ui.panels.data_insp_panel as inspector_module
from src.client.ui.panels.data_insp_panel import DataInspectorPanel


def _imgui_mock(monkeypatch):
    imgui = Mock()
    imgui.TableFlags_ = SimpleNamespace(
        scroll_y=1,
        borders=2,
        row_bg=4,
        resizable=8,
        reorderable=16,
        hideable=32,
        sortable=64,
    )
    imgui.TableColumnFlags_ = SimpleNamespace(width_fixed=1, width_stretch=2)
    imgui.SortDirection_ = SimpleNamespace(ascending=1, descending=2)
    imgui.begin_combo.return_value = False
    imgui.begin_table.return_value = False
    imgui.input_text.return_value = (False, "")
    monkeypatch.setattr(inspector_module, "imgui", imgui)
    return imgui


def test_render_returns_window_state_and_only_draws_when_open(monkeypatch):
    is_open = {"value": False}

    @contextmanager
    def window(*_args, **_kwargs):
        yield is_open["value"]

    monkeypatch.setattr(inspector_module, "WindowManager", SimpleNamespace(window=window))
    panel = DataInspectorPanel()
    panel._render_content = Mock()

    assert panel.render(SimpleNamespace(), None) is False
    panel._render_content.assert_not_called()

    is_open["value"] = True
    state = SimpleNamespace()
    assert panel.render(state, None) is True
    panel._render_content.assert_called_once_with(state)


def test_render_content_reports_empty_game_state(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    panel = DataInspectorPanel()

    panel._render_content(SimpleNamespace())

    imgui.text_disabled.assert_called_once_with("GameState is empty.")
    imgui.separator.assert_called_once_with()


def test_render_content_selects_first_item_when_selection_is_missing(monkeypatch):
    _imgui_mock(monkeypatch)
    state = SimpleNamespace(globals={"first": "value"})
    panel = DataInspectorPanel()
    panel._render_generic_object = Mock()

    panel._render_content(state)

    assert panel.selected_key == "[Global] first"
    panel._render_generic_object.assert_called_once_with("value")


def test_render_content_dispatches_by_selected_data_type(monkeypatch):
    imgui = _imgui_mock(monkeypatch)

    @dataclass
    class Clock:
        year: int

    frame = pl.DataFrame({"country": ["UKR"]})
    state = SimpleNamespace(
        time=Clock(2026),
        tables={"countries": frame},
        globals={"settings": {"theme": "dark"}, "selection": ["UKR"]},
    )
    targets = (
        ("[Obj] Time", "_render_dataclass", state.time),
        ("[Table] countries", "_render_dataframe", frame),
        ("[Global] settings", "_render_dict", state.globals["settings"]),
        ("[Global] selection", "_render_generic_object", state.globals["selection"]),
    )

    for selected_key, method_name, expected in targets:
        panel = DataInspectorPanel()
        panel.selected_key = selected_key
        renderer = Mock()
        setattr(panel, method_name, renderer)

        panel._render_content(state)

        renderer.assert_called_once_with(expected)

    imgui.begin_combo.assert_has_calls(
        [
            (("##InspectorSel", "[Obj] Time"),),
            (("##InspectorSel", "[Table] countries"),),
            (("##InspectorSel", "[Global] settings"),),
            (("##InspectorSel", "[Global] selection"),),
        ]
    )


def test_render_content_updates_selection_from_open_combo(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    imgui.begin_combo.return_value = True
    imgui.selectable.side_effect = lambda key, _selected: (key == "[Global] next", False)
    state = SimpleNamespace(globals={"current": 1, "next": 2})
    panel = DataInspectorPanel()
    panel.selected_key = "[Global] current"
    panel._render_generic_object = Mock()

    panel._render_content(state)

    assert panel.selected_key == "[Global] next"
    imgui.set_item_default_focus.assert_called_once_with()
    imgui.end_combo.assert_called_once_with()
    panel._render_generic_object.assert_called_once_with(2)


def test_render_dataframe_handles_empty_frames_and_closed_tables(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    panel = DataInspectorPanel()

    panel._render_dataframe(pl.DataFrame())
    imgui.text_disabled.assert_called_once_with("Empty DataFrame.")

    imgui.reset_mock()
    imgui.begin_table.return_value = False
    panel._render_dataframe(pl.DataFrame({"id": [1]}))

    imgui.input_text.assert_called_once_with("Search", "")
    imgui.begin_table.assert_called_once_with("DfGrid", 1, 127)
    imgui.table_setup_column.assert_not_called()


def test_update_sort_ignores_clean_and_invalid_specs_and_orders_valid_specs(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    panel = DataInspectorPanel()
    panel._sort_columns = (("old", True),)

    imgui.table_get_sort_specs.return_value = None
    panel._update_sort_from_imgui(["name", "score"])
    assert panel._sort_columns == (("old", True),)

    clean_specs = SimpleNamespace(specs_dirty=False)
    imgui.table_get_sort_specs.return_value = clean_specs
    panel._update_sort_from_imgui(["name", "score"])
    assert panel._sort_columns == (("old", True),)

    class SortSpec:
        def __init__(self, column_index, sort_order, direction):
            self.column_index = column_index
            self.sort_order = sort_order
            self.direction = direction

        def get_sort_direction(self):
            return self.direction

    specs = [
        SortSpec(1, 1, imgui.SortDirection_.descending),
        SortSpec(0, 0, imgui.SortDirection_.ascending),
        SortSpec(-1, 2, imgui.SortDirection_.ascending),
        SortSpec(3, 3, imgui.SortDirection_.descending),
    ]
    dirty_specs = SimpleNamespace(
        specs_dirty=True,
        specs_count=len(specs),
        get_specs=lambda index: specs[index],
    )
    imgui.table_get_sort_specs.return_value = dirty_specs

    panel._update_sort_from_imgui(["name", "score"])

    assert panel._sort_columns == (("name", True), ("score", False))
    assert dirty_specs.specs_dirty is False


def test_display_dataframe_reuses_identity_cache_and_ignores_unknown_sort_columns():
    panel = DataInspectorPanel()
    frame = pl.DataFrame({"name": ["alpha", "beta"]})
    panel._sort_columns = (("missing", True),)

    display = panel._display_data_frame(frame)
    assert display is frame
    assert panel._display_data_frame(frame) is display

    panel._display_source = frame
    panel._display_signature = ("", panel._sort_columns)
    panel._display_frame = None
    assert panel._display_data_frame(frame) is frame


def test_render_dataclass_and_dictionary_rows_and_table_closed_paths(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    panel = DataInspectorPanel()
    panel._draw_value = Mock()

    @dataclass
    class Sample:
        name: str
        count: int

    imgui.begin_table.return_value = True
    sample = Sample("unit", 3)
    panel._render_dataclass(sample)
    imgui.begin_table.assert_called_once_with("DcGrid", 2, 14)
    assert panel._draw_value.call_args_list[0].args == ("unit",)
    assert panel._draw_value.call_args_list[1].args == (3,)
    imgui.end_table.assert_called_once_with()

    imgui.reset_mock()
    imgui.begin_table.return_value = True
    panel._render_dict({"ready": True})
    imgui.begin_table.assert_called_once_with("DictGrid", 2, 14)
    panel._draw_value.assert_called_with(True)
    imgui.end_table.assert_called_once_with()

    imgui.reset_mock()
    imgui.begin_table.return_value = False
    panel._render_dataclass(sample)
    panel._render_dict({"ready": True})
    imgui.end_table.assert_not_called()


def test_draw_value_formats_numeric_none_and_other_values(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    panel = DataInspectorPanel()

    panel._draw_value(12.5)
    imgui.text_colored.assert_called_once_with(inspector_module.GAMETHEME.colors.accent, "12.5")

    imgui.reset_mock()
    panel._draw_value(None)
    imgui.text_disabled.assert_called_once_with("None")

    imgui.reset_mock()
    panel._draw_value("value")
    imgui.text.assert_called_once_with("value")

    panel._render_generic_object({"plain": "text"})
    imgui.text_wrapped.assert_called_once_with("{'plain': 'text'}")


def test_draw_value_uses_boolean_colors_before_numeric_colors(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    panel = DataInspectorPanel()

    panel._draw_value(True)
    imgui.text_colored.assert_called_once_with(inspector_module.GAMETHEME.colors.positive, "True")

    imgui.reset_mock()
    panel._draw_value(False)
    imgui.text_colored.assert_called_once_with(inspector_module.GAMETHEME.colors.negative, "False")
