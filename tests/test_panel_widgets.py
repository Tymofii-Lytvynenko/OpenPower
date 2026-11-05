from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from src.client.ui.core.primitives import UIPrimitives
from src.client.ui.panels.shared.panel_widgets import (
    draw_empty_state,
    draw_key_value_rows,
    draw_required_tables,
)


def test_key_value_rows_delegate_to_shared_aligned_primitive(monkeypatch):
    calls = []

    def record_row(label, value, *, dim_label=True):
        calls.append((label, value, dim_label))

    monkeypatch.setattr(UIPrimitives, "value_row", record_row)

    draw_key_value_rows((("DATE", "2001-01-01"), ("TARGET", "USA")))
    draw_key_value_rows((("F1", "Open help"),), dim_labels=False)

    assert calls == [
        ("DATE", "2001-01-01", True),
        ("TARGET", "USA", True),
        ("F1", "Open help", False),
    ]


def test_required_tables_reports_missing_data_and_stops_panel_rendering(monkeypatch):
    reported = []
    monkeypatch.setattr(
        "src.client.ui.panels.shared.panel_widgets.draw_empty_state",
        reported.append,
    )

    available = draw_required_tables(
        SimpleNamespace(tables={"present": object(), "null": None}),
        ("present", "null", "absent"),
    )

    assert available is False
    assert reported == ["Required game data is unavailable: null, absent."]


def test_required_tables_accepts_present_empty_table():
    assert draw_required_tables(SimpleNamespace(tables={"empty": pl.DataFrame()}), ("empty",)) is True


def test_empty_state_restores_text_wrap_stack_when_drawing_fails():
    native = MagicMock()
    native.text_colored.side_effect = RuntimeError("render failure")

    with (
        patch("src.client.ui.panels.shared.panel_widgets.imgui", native),
        pytest.raises(RuntimeError, match="render failure"),
    ):
        draw_empty_state("Unavailable")

    native.push_text_wrap_pos.assert_called_once_with(0.0)
    native.pop_text_wrap_pos.assert_called_once_with()


@pytest.mark.parametrize(
    ("dim_label", "label_method"),
    ((True, "text_disabled"), (False, "text")),
)
def test_value_row_preserves_label_emphasis(dim_label, label_method):
    native = MagicMock()
    native.get_cursor_pos_x.return_value = 0.0
    native.get_content_region_avail.return_value = SimpleNamespace(x=300.0)
    native.calc_text_size.side_effect = lambda text: SimpleNamespace(x=len(text) * 6.0)
    native.is_item_hovered.return_value = False

    with patch("src.client.ui.core.primitives.imgui", native):
        UIPrimitives.value_row("F1", "Open help", dim_label=dim_label)

    getattr(native, label_method).assert_any_call("F1")
