from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

import src.client.ui.panels.service.console_panel as console_module
import src.client.ui.panels.service.settings_panel as settings_module
from src.client.ui.panels.service.console_panel import ConsolePanel
from src.client.ui.panels.service.settings_panel import SettingsPanel


def test_console_lists_runtime_and_table_metrics_when_table_is_available(monkeypatch):
    imgui = Mock()
    imgui.TableFlags_.borders = 1
    imgui.TableFlags_.row_bg = 2
    imgui.TableFlags_.scroll_y = 4
    imgui.TableColumnFlags_.width_fixed = 8
    imgui.begin_table.return_value = True
    monkeypatch.setattr(console_module, "imgui", imgui)
    rows = Mock()
    monkeypatch.setattr(console_module, "draw_key_value_rows", rows)
    state = SimpleNamespace(
        time=SimpleNamespace(date_str="1936.01.01"),
        tables={"small": pl.DataFrame({"x": [1]}), "large": pl.DataFrame({"x": [1, 2], "y": [3, 4]})},
        events=[1, 2],
        current_actions=[1],
        journal=SimpleNamespace(domain_events=[1, 2, 3], command_results=[1]),
    )
    context = SimpleNamespace(target_tag="USA")

    ConsolePanel()._render_content(state, context)

    assert rows.call_args.args[0] == (
        ("DATE", "1936.01.01"), ("TARGET", "USA"), ("TABLES", "2"),
        ("EVENTS", "2"), ("ACTIONS", "1"), ("DOMAIN LOG", "3"), ("COMMAND LOG", "1"),
    )
    assert [call.args[0] for call in imgui.text.call_args_list] == [
        "large", "2", "2", "small", "1", "1",
    ]
    imgui.table_setup_column.assert_any_call("ROWS", 8, 90.0)
    imgui.end_table.assert_called_once()


def test_console_skips_table_rendering_when_imgui_cannot_open_the_table(monkeypatch):
    imgui = Mock()
    imgui.TableFlags_.borders = 1
    imgui.TableFlags_.row_bg = 2
    imgui.TableFlags_.scroll_y = 4
    imgui.begin_table.return_value = False
    monkeypatch.setattr(console_module, "imgui", imgui)
    monkeypatch.setattr(console_module, "draw_key_value_rows", Mock())
    state = SimpleNamespace(
        time=SimpleNamespace(date_str="date"), tables={}, events=[], current_actions=[],
        journal=SimpleNamespace(domain_events=[], command_results=[]),
    )

    ConsolePanel()._render_content(state, SimpleNamespace(target_tag="USA"))

    imgui.table_setup_column.assert_not_called()
    imgui.end_table.assert_not_called()


def test_console_render_respects_window_visibility(monkeypatch):
    opened = False

    @contextmanager
    def window(*_args, **_kwargs):
        yield opened

    monkeypatch.setattr(console_module.WindowManager, "window", window)
    panel = ConsolePanel()
    panel._render_content = Mock()
    state, context = SimpleNamespace(), SimpleNamespace()

    assert panel.render(state, context) is False
    opened = True
    assert panel.render(state, context) is True
    panel._render_content.assert_called_once_with(state, context)


def test_settings_render_reports_missing_service_or_renders_available_content(monkeypatch):
    opened = True

    @contextmanager
    def window(*_args, **_kwargs):
        yield opened

    monkeypatch.setattr(settings_module.WindowManager, "window", window)
    imgui = SimpleNamespace(text_disabled=Mock())
    monkeypatch.setattr(settings_module, "imgui", imgui)
    missing = SettingsPanel(None, None)
    assert missing.render(SimpleNamespace(), SimpleNamespace()) is True
    imgui.text_disabled.assert_called_once_with("Settings unavailable.")

    service, native_window = object(), object()
    content = SimpleNamespace(render=Mock())
    factory = Mock(return_value=content)
    monkeypatch.setattr(settings_module, "GameSettingsContent", factory)
    available = SettingsPanel(service, native_window)
    assert factory.call_args.args == (service, native_window)
    assert available.render(SimpleNamespace(), SimpleNamespace()) is True
    content.render.assert_called_once_with()

    opened = False
    assert available.render(SimpleNamespace(), SimpleNamespace()) is False
    assert content.render.call_count == 1
