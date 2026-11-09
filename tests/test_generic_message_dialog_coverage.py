from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.components.shared.generic_message_dialog as dialog_module
from src.client.ui.components.shared.generic_message_dialog import GenericMessageDialog


def _install_render_doubles(monkeypatch, *, window_open=True, body_open=True, acknowledged=False):
    viewport = SimpleNamespace(
        pos=SimpleNamespace(x=20.0, y=30.0),
        size=SimpleNamespace(x=1000.0, y=800.0),
    )
    imgui = SimpleNamespace(
        get_main_viewport=Mock(return_value=viewport),
        WindowFlags_=SimpleNamespace(
            no_title_bar=1,
            no_resize=2,
            no_collapse=4,
            no_saved_settings=8,
            no_scrollbar=16,
            no_scroll_with_mouse=32,
        ),
        Col_=SimpleNamespace(text=7),
        set_next_window_focus=Mock(),
        push_style_color=Mock(),
        text_wrapped=Mock(),
        pop_style_color=Mock(),
        button=Mock(return_value=acknowledged),
    )
    window = Mock(side_effect=lambda *_args, **_kwargs: nullcontext(window_open))
    window_manager = SimpleNamespace(window=window)
    geometry = SimpleNamespace(window_width=420.0, window_height=300.0)
    measure = Mock(return_value=geometry)
    layout = object()
    apply_geometry = Mock()
    child_frame = Mock(side_effect=lambda *_args, **_kwargs: nullcontext(body_open))

    monkeypatch.setattr(dialog_module, "imgui", imgui)
    monkeypatch.setattr(dialog_module, "WindowManager", window_manager)
    monkeypatch.setattr(dialog_module, "measure_gml_message_geometry", measure)
    monkeypatch.setattr(dialog_module, "active_gml_layout", Mock(return_value=layout))
    monkeypatch.setattr(dialog_module, "apply_gml_message_geometry", apply_geometry)
    monkeypatch.setattr(dialog_module, "gml_child_frame", child_frame)
    return imgui, window, geometry, measure, layout, apply_geometry, child_frame


def test_empty_messages_are_ignored_and_unknown_severity_defaults_to_info():
    dialog = GenericMessageDialog()

    dialog.enqueue("Ignored", "  \n ")
    assert not dialog.is_open
    dialog.show("Ignored", " \t ")
    assert not dialog.is_open

    dialog.show("  ", "  Notice body  ", severity="urgent")

    assert dialog._content.title == "Message"
    assert dialog._content.message == "Notice body"
    assert dialog._content.severity == "info"


def test_render_returns_false_when_closed_or_without_content(monkeypatch):
    dialog = GenericMessageDialog()
    assert dialog.render() is False

    imgui, window, *_ = _install_render_doubles(monkeypatch, window_open=False)
    dialog.show("Notice", "The window was closed.")

    assert dialog.render() is False
    assert not dialog.is_open
    imgui.get_main_viewport.assert_called_once()
    assert window.call_count == 1


def test_render_positions_and_draws_the_message_without_acknowledging(monkeypatch):
    dialog = GenericMessageDialog()
    dialog.show("Warning", "A longer message.", severity="WARNING")
    imgui, window, geometry, measure, layout, apply_geometry, child_frame = (
        _install_render_doubles(monkeypatch)
    )

    assert dialog.render() is True

    measure.assert_called_once_with(
        "Generic_Message_Window",
        "Warning\nA longer message.",
        800.0,
    )
    window.assert_called_once_with(
        "##generic_message_dialog",
        x=310.0,
        y=280.0,
        w=420.0,
        h=300.0,
        flags=63,
        test_id="generic_message.dialog",
        gml_template="Generic_Message_Window",
        size_override=(420.0, 300.0),
    )
    apply_geometry.assert_called_once_with(layout, geometry)
    child_frame.assert_called_once_with(
        "Generic_Message_Window/lblMessage",
        padding=(0, 0),
        bordered=False,
    )
    imgui.push_style_color.assert_called_once_with(
        imgui.Col_.text,
        dialog._COLORS["warning"],
    )
    imgui.text_wrapped.assert_called_once_with(
        "Warning\nA longer message.",
        test_id="generic_message.content",
    )
    imgui.pop_style_color.assert_called_once_with()
    imgui.button.assert_called_once_with(
        "OK",
        test_id="generic_message.ok",
        gml_id="Generic_Message_Window/btnOk",
    )


def test_render_acknowledges_when_the_ok_button_is_pressed(monkeypatch):
    dialog = GenericMessageDialog()
    callback_states = []
    dialog.show(
        "Notice",
        "Acknowledge this message.",
        on_acknowledge=lambda: callback_states.append(dialog.is_open),
    )
    imgui, *_ = _install_render_doubles(monkeypatch, acknowledged=True)

    assert dialog.render() is False

    assert callback_states == [False]
    assert not dialog.is_open
    imgui.button.assert_called_once()
