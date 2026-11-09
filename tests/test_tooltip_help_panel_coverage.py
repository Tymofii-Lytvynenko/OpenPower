from contextlib import contextmanager
from unittest.mock import Mock

import src.client.ui.panels.service.tooltip_help_panel as tooltip_module
from src.client.ui.panels.service.tooltip_help_panel import TooltipHelpPanel


def test_render_skips_closed_window_and_renders_open_window(monkeypatch):
    window_state = {"open": False}

    @contextmanager
    def window(*_args, **_kwargs):
        yield window_state["open"]

    monkeypatch.setattr(tooltip_module.WindowManager, "window", window)
    panel = TooltipHelpPanel()
    panel._render_content = Mock()

    assert panel.render(None, None) is False
    panel._render_content.assert_not_called()

    window_state["open"] = True
    assert panel.render(None, None) is True
    panel._render_content.assert_called_once_with()


def test_content_disables_tours_without_callback(monkeypatch):
    imgui = Mock()
    imgui.button.return_value = False
    monkeypatch.setattr(tooltip_module, "imgui", imgui)
    draw_rows = Mock()
    monkeypatch.setattr(tooltip_module, "draw_key_value_rows", draw_rows)

    TooltipHelpPanel()._render_content()

    imgui.begin_disabled.assert_called_once_with(True)
    imgui.end_disabled.assert_called_once_with()
    imgui.text_wrapped.assert_called_once()
    assert imgui.separator.call_count == 2
    imgui.text.assert_called_once_with("Guided tours")
    draw_rows.assert_called_once()
    assert draw_rows.call_args.kwargs == {"dim_labels": False}
    assert [call.kwargs["test_id"] for call in imgui.button.call_args_list] == [
        "help.tutorial.interface",
        "help.tutorial.military",
    ]


def test_content_opens_each_selected_tour(monkeypatch):
    imgui = Mock()
    imgui.button.side_effect = [True, True]
    monkeypatch.setattr(tooltip_module, "imgui", imgui)
    monkeypatch.setattr(tooltip_module, "draw_key_value_rows", Mock())
    open_tutorial = Mock()

    TooltipHelpPanel(open_tutorial)._render_content()

    imgui.begin_disabled.assert_called_once_with(False)
    imgui.same_line.assert_called_once_with()
    imgui.end_disabled.assert_called_once_with()
    assert [call.args[0] for call in open_tutorial.call_args_list] == [
        "interface",
        "military",
    ]
