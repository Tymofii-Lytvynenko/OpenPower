from __future__ import annotations

from unittest.mock import Mock, patch

import polars as pl
from imgui_bundle import imgui

from src.client.ui.panels.data_insp_panel import DataInspectorPanel


def test_data_inspector_filters_literal_case_insensitive_matches_across_columns() -> None:
    panel = DataInspectorPanel()
    panel.search_text = "covid["
    frame = pl.DataFrame(
        {
            "country": ["A", "B", "C"],
            "event": ["Nothing", "COVID[19] response", "other"],
        }
    )

    result = panel._display_data_frame(frame)

    assert result.get_column("country").to_list() == ["B"]


def test_data_inspector_sorts_with_stable_nulls_last_order() -> None:
    panel = DataInspectorPanel()
    panel._sort_columns = (("score", True),)
    frame = pl.DataFrame(
        {
            "name": ["later", "first", "also first", "missing"],
            "score": [2, 1, 1, None],
        }
    )

    result = panel._display_data_frame(frame)

    assert result.get_column("name").to_list() == ["first", "also first", "later", "missing"]


def test_table_sort_specs_are_applied_and_marked_clean() -> None:
    panel = DataInspectorPanel()

    class Spec:
        column_index = 1
        sort_order = 0

        @staticmethod
        def get_sort_direction():
            return imgui.SortDirection_.descending

    class Specs:
        specs_dirty = True
        specs_count = 1

        @staticmethod
        def get_specs(index: int) -> Spec:
            assert index == 0
            return Spec()

    specs = Specs()
    with patch.object(imgui, "table_get_sort_specs", return_value=specs):
        panel._update_sort_from_imgui(["name", "score"])

    assert panel._sort_columns == (("score", False),)
    assert specs.specs_dirty is False


def test_data_inspector_uses_imgui_clipper_for_visible_rows_only() -> None:
    panel = DataInspectorPanel()
    frame = pl.DataFrame({"id": range(10_000), "name": ["nation"] * 10_000})
    drawn_values = Mock()

    class Clipper:
        display_start = 100
        display_end = 102

        def __init__(self) -> None:
            self.finished = False
            self.item_count = 0

        def begin(self, item_count: int) -> None:
            self.item_count = item_count

        def step(self) -> bool:
            if self.finished:
                return False
            self.finished = True
            return True

    with (
        patch.object(imgui, "set_next_item_width"),
        patch.object(imgui, "input_text", return_value=(False, "")),
        patch.object(imgui, "same_line"),
        patch.object(imgui, "text_disabled"),
        patch.object(imgui, "begin_table", return_value=True),
        patch.object(imgui, "table_setup_column"),
        patch.object(imgui, "table_headers_row"),
        patch.object(imgui, "table_get_sort_specs", return_value=None),
        patch.object(imgui, "ListClipper", Clipper),
        patch.object(imgui, "table_next_row"),
        patch.object(imgui, "table_next_column"),
        patch.object(imgui, "end_table"),
        patch.object(panel, "_draw_value", drawn_values),
    ):
        panel._render_dataframe(frame)

    assert drawn_values.call_count == 4
