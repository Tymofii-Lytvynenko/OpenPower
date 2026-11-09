from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from src.client.ui.core.primitives import GAMETHEME, UIPrimitives, UnitCompositionRow


def _theme():
    return SimpleNamespace(
        colors=SimpleNamespace(
            bg_input=(0.1, 0.2, 0.3, 1.0),
            interaction_active=(0.2, 0.3, 0.4, 1.0),
            text_dim=(0.5, 0.5, 0.5, 1.0),
            text_main=(0.9, 0.9, 0.9, 1.0),
            panel_bg_dark=(0.02, 0.03, 0.04, 1.0),
        )
    )


def test_fit_text_returns_empty_when_ellipsis_cannot_fit():
    native = MagicMock()
    native.calc_text_size.side_effect = lambda text: SimpleNamespace(x=len(text) * 6)

    with patch("src.client.ui.core.primitives.imgui", native):
        result = UIPrimitives.fit_text("A long label", 12)

    assert result == ""
    native.calc_text_size.assert_has_calls([call("A long label"), call("...")])


def test_invisible_button_uses_test_id_as_fallback_label_and_records_disabled_state():
    native = MagicMock()
    native.invisible_button.return_value = True
    record = MagicMock()

    with (
        patch("src.client.ui.core.primitives.imgui", native),
        patch("src.client.ui.core.primitives.record_last_item", record),
    ):
        clicked = UIPrimitives.invisible_button(
            (16, 16), test_id="map.target", enabled=False, gml_id="Map/target"
        )

    assert clicked is True
    native.invisible_button.assert_called_once_with(
        "map.target###map.target", (16, 16), gml_id="Map/target"
    )
    record.assert_called_once_with(
        "map.target", "map.target", "invisible_button", enabled=False
    )


def test_slider_float_preserves_stable_identity_and_disabled_telemetry():
    native = MagicMock()
    native.slider_float.return_value = (True, 7.5)
    record = MagicMock()

    with (
        patch("src.client.ui.core.primitives.imgui", native),
        patch("src.client.ui.core.primitives.record_last_item", record),
    ):
        result = UIPrimitives.slider_float(
            "Volume",
            5.0,
            0.0,
            10.0,
            "%.1f",
            test_id="audio.volume",
            enabled=False,
            gml_id="Audio/volume",
        )

    assert result == (True, 7.5)
    native.slider_float.assert_called_once_with(
        "Volume###audio.volume",
        5.0,
        0.0,
        10.0,
        "%.1f",
        gml_id="Audio/volume",
    )
    record.assert_called_once_with(
        "audio.volume", "Volume", "slider_float", enabled=False
    )


def test_header_without_background_draws_text_and_separator():
    native = MagicMock()

    with patch("src.client.ui.core.primitives.imgui", native):
        UIPrimitives.header("DETAILS", show_bg=False, theme=_theme())

    native.text_colored.assert_called_once_with(_theme().colors.text_main, "DETAILS")
    native.separator.assert_called_once_with()
    native.get_cursor_screen_pos.assert_not_called()


def test_value_row_uses_dim_label_for_compact_display():
    native = MagicMock()
    native.get_cursor_pos_x.return_value = 2.0
    native.get_content_region_avail.return_value = SimpleNamespace(x=120.0)
    native.calc_text_size.side_effect = lambda text: SimpleNamespace(x=len(text) * 6.0)

    with patch("src.client.ui.core.primitives.imgui", native):
        UIPrimitives.value_row("Balance", "42")

    native.text_disabled.assert_called_once_with("Balance")
    native.text.assert_not_called()
    native.same_line.assert_called_once_with(104.0)


def test_meter_row_clamps_width_and_value_and_draws_default_value_text():
    native = MagicMock()
    native.get_cursor_pos_x.return_value = 3.0
    native.get_content_region_avail.side_effect = [
        SimpleNamespace(x=160.0),
        SimpleNamespace(x=160.0),
    ]
    native.get_cursor_screen_pos.return_value = SimpleNamespace(x=12.0, y=24.0)
    native.calc_text_size.side_effect = lambda text: SimpleNamespace(x=len(text) * 5.0)
    draw_horizontal_bar = MagicMock()
    color = (0.3, 0.8, 0.4, 1.0)

    with (
        patch("src.client.ui.core.primitives.imgui", native),
        patch.object(UIPrimitives, "_draw_horizontal_bar", draw_horizontal_bar),
    ):
        UIPrimitives.meter_row("Health", 120.0, color, label_width=300.0)

    native.text_disabled.assert_called_once_with("Health")
    native.same_line.assert_has_calls([call(83.0), call()])
    draw_horizontal_bar.assert_called_once_with(
        native.get_window_draw_list.return_value,
        SimpleNamespace(x=12.0, y=24.0),
        117.0,
        12.0,
        1.0,
        GAMETHEME.colors.bg_input,
        color,
        rounding=6.0,
    )
    native.text_colored.assert_called_once_with(color, "120.0 %")


def test_right_align_text_without_color_restores_full_text_in_tooltip():
    native = MagicMock()
    native.get_content_region_avail.return_value = SimpleNamespace(x=12.0)
    native.get_cursor_pos_x.return_value = 4.0
    native.calc_text_size.side_effect = lambda text: SimpleNamespace(x=len(text) * 6.0)
    native.is_item_hovered.return_value = True

    with patch("src.client.ui.core.primitives.imgui", native):
        UIPrimitives.right_align_text("Long label")

    native.text.assert_called_once_with("")
    native.text_colored.assert_not_called()
    native.set_tooltip.assert_called_once_with("Long label")
    native.set_cursor_pos_x.assert_called_once_with(16.0)


def test_icon_toggle_records_accessible_name_and_draws_inactive_indicator():
    native = MagicMock()
    native.get_item_rect_min.return_value = SimpleNamespace(x=10.0, y=20.0)
    native.get_item_rect_max.return_value = SimpleNamespace(x=60.0, y=70.0)
    native.get_color_u32.side_effect = lambda color: color
    record = MagicMock()
    theme = _theme()

    with (
        patch("src.client.ui.core.primitives.imgui", native),
        patch("src.client.ui.core.primitives.record_last_item", record),
    ):
        clicked = UIPrimitives.icon_toggle(
            "⚙",
            (0.1, 0.8, 0.2, 1.0),
            False,
            show_inactive_indicator=True,
            test_id="settings.toggle",
            accessible_label="Open settings",
            theme=theme,
        )

    assert clicked is native.button.return_value
    native.button.assert_called_once_with(
        "⚙###settings.toggle", (50, 50), gml_id=None
    )
    record.assert_called_once_with("settings.toggle", "Open settings", "button")
    native.get_window_draw_list.return_value.add_rect_filled.assert_called_once_with(
        (15.0, 64.0),
        (55.0, 68.0),
        theme.colors.text_dim,
        2.0,
    )


def test_unit_composition_plate_clamps_values_and_skips_zero_width_fill():
    native = MagicMock()
    native.get_color_u32.side_effect = lambda color: color
    draw_list = MagicMock()
    rows = (
        UnitCompositionRow("Reserve", -3, (0.2, 0.4, 0.6, 1.0)),
        UnitCompositionRow("Infantry", 5, (0.8, 0.3, 0.2, 1.0)),
    )

    with patch("src.client.ui.core.primitives.imgui", native):
        UIPrimitives.unit_composition_plate(draw_list, 2.0, 4.0, rows)

    texts = [entry.args[2] for entry in draw_list.add_text.call_args_list]
    assert texts == ["Reserve", "0", "Infantry", "5"]
    fill_rectangles = [
        entry
        for entry in draw_list.add_rect_filled.call_args_list
        if entry.args[2] == rows[1].color
    ]
    assert len(fill_rectangles) == 1
    assert fill_rectangles[0].args[1] == (51.0, 28.0)
    assert fill_rectangles[0].args[2] == rows[1].color


def test_unit_composition_plate_handles_empty_rows_and_nonpositive_maximum():
    native = MagicMock()
    native.get_color_u32.side_effect = lambda color: color
    draw_list = MagicMock()

    with patch("src.client.ui.core.primitives.imgui", native):
        UIPrimitives.unit_composition_plate(draw_list, 0, 0, ())
        UIPrimitives.unit_composition_plate(
            draw_list,
            0,
            0,
            (UnitCompositionRow("Cavalry", 10, (1.0, 0.0, 0.0, 1.0)),),
            max_value=0,
        )

    assert draw_list.add_text.call_args_list[-1].args[2] == "10"
    assert draw_list.add_rect_filled.call_args_list[-1].args[1] == (49.0, 13.0)


def test_dark_child_box_cleans_up_styles_when_child_is_open_or_collapsed():
    native = MagicMock()
    events = []
    visibility = []
    begin_results = iter([True, False])
    native.push_style_color.side_effect = lambda *args: events.append("push_color")
    native.push_style_var.side_effect = lambda *args: events.append("push_var")
    native.begin_child.side_effect = lambda *args: events.append("begin") or next(
        begin_results
    )
    native.end_child.side_effect = lambda: events.append("end")
    native.pop_style_var.side_effect = lambda: events.append("pop_var")
    native.pop_style_color.side_effect = lambda: events.append("pop_color")
    with patch("src.client.ui.core.primitives.imgui", native):
        with UIPrimitives.dark_child_box("open") as visible:
            visibility.append(visible)
            events.append("body")
        with UIPrimitives.dark_child_box("collapsed", border=False) as visible:
            visibility.append(visible)
            if visible:
                events.append("body")

    assert visibility == [True, False]

    assert events == [
        "push_color", "push_var", "begin", "body", "end", "pop_var", "pop_color",
        "push_color", "push_var", "begin", "end", "pop_var", "pop_color",
    ]


def test_combo_row_aligns_label_and_returns_selected_index():
    native = MagicMock()
    native.get_cursor_pos_x.return_value = 12.0
    native.combo.return_value = (True, 2)

    with patch("src.client.ui.core.primitives.imgui", native):
        selected = UIPrimitives.combo_row("Policy", 1, ["Open", "Closed"], 96.0)

    assert selected == 2
    native.text_disabled.assert_called_once_with("Policy")
    native.same_line.assert_called_once_with(108.0)
    native.set_next_item_width.assert_called_once_with(-1)
    native.combo.assert_called_once_with("##Policy", 1, ["Open", "Closed"])
