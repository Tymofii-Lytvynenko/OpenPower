from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from src.client.ui.core import gml_widgets as widgets_module
from src.client.ui.core.gml_widgets import GMLWidgets


def component(path, *, x=10, y=20, width=40, height=16, font_size=None,
              text_offset=(0.0, 0.0), parent=None, kind="image"):
    rect = SimpleNamespace(x=x, y=y, width=width, height=height)
    return SimpleNamespace(
        path=path,
        local_rect=rect,
        rect=rect,
        font_size=font_size,
        text_offset=text_offset,
        parent=parent,
        kind=kind,
    )


def session_for(*components):
    by_path = {item.path: item for item in components}
    layout = SimpleNamespace(
        components=list(components),
        component=lambda path: by_path.get(path),
    )
    return SimpleNamespace(
        layout=layout,
        window_position=(100.0, 200.0),
        rect_for=lambda item: item.rect,
    )


def install_imgui(monkeypatch, *, session=None):
    native = MagicMock()
    native.StyleVar_.frame_padding = "frame_padding"
    native.HoveredFlags_.allow_when_disabled = "allow_when_disabled"
    native.get_cursor_screen_pos.return_value = (3.0, 4.0)
    native.get_scroll_x.return_value = 5.0
    native.get_scroll_y.return_value = 7.0
    native.get_style.return_value = SimpleNamespace(font_scale_main=2.0, font_scale_dpi=1.5)
    native.get_color_u32.side_effect = lambda color: color
    native.get_window_draw_list.return_value = MagicMock()
    native.is_item_hovered.return_value = False
    native.is_item_active.return_value = False
    native.invisible_button.return_value = False
    native.button.return_value = False
    native.combo.return_value = (False, 0)
    native.input_float.return_value = (False, 1.0)
    native.calc_text_size.return_value = SimpleNamespace(x=8.0, y=8.0)
    native.get_item_rect_min.return_value = SimpleNamespace(x=10.0, y=0.0)
    native.get_item_rect_max.return_value = SimpleNamespace(x=110.0, y=20.0)
    native.get_io.return_value.mouse_pos.x = 75.0
    monkeypatch.setattr(widgets_module, "imgui", native)
    monkeypatch.setattr(widgets_module, "active_gml_layout", lambda: session)
    monkeypatch.setattr(widgets_module, "suspend_gml_layout", lambda: "layout-token")
    monkeypatch.setattr(widgets_module, "resume_gml_layout", Mock())
    monkeypatch.setattr(widgets_module.UIPrimitives, "fit_text", lambda text, _width: text)
    return native


def test_unanchored_widgets_return_safe_defaults_without_open_layout(monkeypatch):
    native = install_imgui(monkeypatch)
    ui = GMLWidgets("Window/")
    assert ui.root == "Window"
    assert ui.path("slot") == "Window/slot"
    assert ui.rect("slot") is None

    ui.frame("slot")
    ui.picture("slot", Mock())
    ui.rule("slot")
    ui.text_at("slot", "ignored")
    assert ui.hitbox_state("slot", "test") == (False, False)
    assert ui.hitbox("slot", "test") is False
    assert ui.button_at("slot", "Click", "test") is False
    assert ui.arrow_button_state("slot", "up", "test") == (False, False)
    assert ui.arrow_button("slot", "down", "test") is False
    assert ui.combo_at("slot", "Pick", 2, ["a"], "test") == (False, 2)
    assert ui.toggle("slot", True, "test", icon="x", color=(1, 1, 1, 1)) == (False, True)
    ui.meter("slot", 0.5, (1, 1, 1, 1))
    ui.segmented_meter("slot", 0.5, (1, 1, 1, 1), "test")
    assert ui.meter_slider("slot", 0.5, "test", (1, 1, 1, 1)) == (False, 0.5)
    assert native.get_window_draw_list.call_count == 0


def test_frame_picture_rule_and_text_use_source_geometry_and_restore_cursor(monkeypatch):
    item = component("Window/slot", width=60, height=10, font_size=12, text_offset=(3, 0))
    session = session_for(item)
    native = install_imgui(monkeypatch, session=session)
    native.is_item_hovered.return_value = True
    ui = GMLWidgets("Window")
    draw = Mock()

    ui.frame("slot")
    draw_fn = Mock()
    ui.picture("slot", draw_fn)
    ui.rule("slot", (0.1, 0.2, 0.3, 1.0))
    ui.text("slot", 42, color=(1, 1, 1, 1), max_width=35, tooltip="full text", right=True)

    native_draw = native.get_window_draw_list.return_value
    assert native_draw.add_rect_filled.call_count == 1
    assert native_draw.add_rect.call_count == 1
    assert draw_fn.call_args.args == (60, 10)
    assert native.set_cursor_screen_pos.call_args_list[0].args == ((105.0, 213.0),)
    assert native.set_cursor_screen_pos.call_args_list[-1].args == ((3.0, 4.0),)
    native_draw.add_line.assert_called_once()
    native.push_font.assert_called_once_with(None, 4.0)
    native.pop_font.assert_called_once()
    native.set_tooltip.assert_called_once_with("full text")
    native.text_colored.assert_called_once_with(
        (1, 1, 1, 1), "42", gml_id="Window/slot", gml_align="right", test_id=None
    )


def test_picture_restores_cursor_when_draw_callback_fails(monkeypatch):
    item = component("Window/slot")
    install_imgui(monkeypatch, session=session_for(item))
    ui = GMLWidgets("Window")

    with pytest.raises(RuntimeError, match="texture failed"):
        ui.picture("slot", Mock(side_effect=RuntimeError("texture failed")))

    native = widgets_module.imgui
    assert native.set_cursor_screen_pos.call_args_list[-1].args == ((3.0, 4.0),)


def test_text_at_temporarily_suspends_layout_and_restores_state(monkeypatch):
    item = component("Window/slot", width=60, font_size=15)
    session = session_for(item)
    native = install_imgui(monkeypatch, session=session)
    native.is_item_hovered.return_value = True
    ui = GMLWidgets("Window")
    ui.text_at("slot", "dynamic", offset=(4, 2), tooltip="why disabled", test_id="item")

    assert native.set_cursor_screen_pos.call_args_list[0].args == ((109.0, 215.0),)
    assert native.set_cursor_screen_pos.call_args_list[-1].args == ((3.0, 4.0),)
    assert widgets_module.resume_gml_layout.call_args.args == ("layout-token",)
    native.push_font.assert_called_once_with(None, 5.0)
    native.set_tooltip.assert_called_once_with("why disabled")
    native.text_colored.assert_called_once_with(
        widgets_module.GAMETHEME.colors.text_main, "dynamic", test_id="item"
    )


def test_hitboxes_buttons_arrows_and_combos_forward_state_and_tooltips(monkeypatch):
    item = component("Window/slot", width=8, height=9)
    session = session_for(item)
    native = install_imgui(monkeypatch, session=session)
    native.invisible_button.return_value = True
    native.is_item_active.return_value = True
    native.is_item_hovered.return_value = True
    native.button.return_value = True
    native.combo.return_value = (True, 1)
    ui = GMLWidgets("Window")

    assert ui.hitbox_state("slot", "hit", tooltip="disabled", width=30, height=-1) == (True, True)
    assert ui.hitbox("slot", "hit") is True
    assert ui.button_at("slot", "Go", "go", offset=(2, 3), size=(50, 16), tooltip="explain") is True
    assert ui.arrow_button_state("slot", "up", "up", tooltip="up") == (True, True)
    assert ui.arrow_button_at((10, 20), (8, 9), "up", "absolute") is True
    assert ui.arrow_button_at_state((10, 20), (8, 9), "down", "down") == (True, True)
    assert ui.combo_at("slot", "Country", 0, ["A", "B"], "country", enabled=False) == (True, 1)

    with pytest.raises(ValueError, match="Arrow direction"):
        ui.arrow_button_state("slot", "left", "bad")
    with pytest.raises(ValueError, match="Arrow direction"):
        ui.arrow_button_at_state((0, 0), (10, 10), "left", "bad-absolute")

    native.set_tooltip.assert_any_call("disabled")
    native.set_tooltip.assert_any_call("explain")
    native.set_tooltip.assert_any_call("up")
    assert native.get_window_draw_list.return_value.add_triangle_filled.call_count == 3
    native.combo.assert_called_once_with(
        "Country", 0, ["A", "B"], test_id="country", gml_id="Window/slot"
    )


def test_toggle_updates_persisted_value_and_draws_control(monkeypatch):
    item = component("Window/toggle", width=30, height=20)
    native = install_imgui(monkeypatch, session=session_for(item))
    native.invisible_button.return_value = True
    native.is_item_hovered.return_value = True
    persist = Mock()
    monkeypatch.setattr(widgets_module, "set_widget_value", persist)
    ui = GMLWidgets("Window")

    assert ui.toggle(
        "toggle", False, "feature.enabled", icon="✓", color=(0.2, 0.4, 0.6, 1),
        tooltip="Feature is enabled",
    ) == (True, True)

    persist.assert_called_once_with("feature.enabled", True)
    native.get_window_draw_list.return_value.add_rect_filled.assert_called_once()
    native.get_window_draw_list.return_value.add_rect.assert_called_once()
    native.get_window_draw_list.return_value.add_text.assert_called_once()
    native.set_tooltip.assert_called_once_with("Feature is enabled")


def test_meters_clamp_fraction_draw_cursor_marker_and_segment_fills(monkeypatch):
    bar = component("Window/bar", x=10, y=20, width=100, height=10)
    marker = component("Window/marker", x=70, y=40, width=4, height=8)
    segmented = component("Window/segments", x=0, y=0, width=50, height=10)
    empty_segmented = component("Window/empty", x=0, y=0, width=20, height=10)
    first = component("Window/segments/one", x=0, y=0, width=10, height=8,
                      parent="Window/segments", kind="frame")
    second = component("Window/segments/two", x=12, y=0, width=10, height=8,
                       parent="Window/segments", kind="frame")
    native = install_imgui(
        monkeypatch, session=session_for(bar, marker, segmented, empty_segmented, first, second)
    )
    ui = GMLWidgets("Window")
    ui.hitbox = Mock(return_value=False)

    ui.meter("bar", -0.5, (1, 0, 0, 1), cursor=True, max_width=80,
             background_color=(0, 0, 0, 1), marker_slot="marker")
    ui.meter("bar", 0.5, (0, 1, 0, 1), cursor=False)
    ui.segmented_meter("segments", 0.75, (0, 0, 1, 1), "segmented", tooltip="meter")
    ui.segmented_meter("empty", 0.5, (0, 0, 1, 1), "empty")

    draw = native.get_window_draw_list.return_value
    assert draw.add_rect_filled.call_count >= 8
    ui.hitbox.assert_called_once_with("segments", "segmented", tooltip="meter")


def test_meter_slider_reports_active_pointer_ratio_and_draws_cursor(monkeypatch):
    item = component("Window/bar", x=10, y=20, width=100, height=12)
    native = install_imgui(monkeypatch, session=session_for(item))
    ui = GMLWidgets("Window")
    ui.meter = Mock()

    assert ui.meter_slider("bar", 0.2, "ratio", (1, 1, 1, 1)) == (False, 0.2)
    native.is_item_active.return_value = True
    native.is_item_hovered.return_value = True
    native.get_io.return_value.mouse_pos.x = 75.0
    assert ui.meter_slider(
        "bar", 0.2, "ratio", (1, 1, 1, 1), tooltip="drag", show_cursor=True
    ) == (True, 0.65)
    ui.meter.assert_called_with("bar", 0.65, (1, 1, 1, 1))
    native.set_tooltip.assert_called_once_with("drag")
    assert native.get_window_draw_list.return_value.add_rect_filled.call_count == 2
