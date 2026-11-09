from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.components.shared.loading_status_panel as loading_module
from src.client.ui.components.shared.loading_status_panel import LoadingStatusPanel


def test_render_shows_progress_when_no_error_is_present(monkeypatch):
    ui = Mock()
    ui.begin_centered_panel.return_value = True
    monkeypatch.setattr(loading_module, "imgui", Mock())
    task = SimpleNamespace(progress=0.4, status_text="Loading world")

    LoadingStatusPanel().render(ui, task, None, (1280, 720), Mock())

    ui.begin_centered_panel.assert_called_once_with(
        "Loader", 1280, 720, w=400, h=150,
        test_id="loading.progress.panel", force_size=False,
    )
    ui.draw_title.assert_called_once_with("PROCESSING")
    ui.draw_progress_bar.assert_called_once_with(0.4, "Loading world")
    ui.end_panel.assert_called_once_with()


def test_render_sizes_error_panel_and_invokes_return_callback(monkeypatch):
    ui = Mock()
    ui.begin_centered_panel.side_effect = [True, True]
    imgui = Mock()
    imgui.button.side_effect = [False, True]
    monkeypatch.setattr(loading_module, "imgui", imgui)
    on_return = Mock()
    panel = LoadingStatusPanel()

    panel.render(ui, None, RuntimeError("failed"), (1280, 720), on_return)
    assert on_return.call_count == 0
    panel.render(ui, None, RuntimeError("x" * 100), (1280, 160), on_return)

    assert [call.kwargs for call in ui.begin_centered_panel.call_args_list] == [
        {"w": 400, "h": 150, "test_id": "loading.error.panel", "force_size": True},
        {"w": 400, "h": 120, "test_id": "loading.error.panel", "force_size": True},
    ]
    imgui.text_colored.assert_called_with(
        loading_module.GAMETHEME.colors.error,
        "OPERATION FAILED",
        test_id="loading.error.heading",
    )
    assert imgui.text_wrapped.call_args_list[0].args == ("failed",)
    assert imgui.text_wrapped.call_args_list[1].args == ("x" * 100,)
    assert on_return.call_count == 1
    assert ui.end_panel.call_count == 2


def test_render_skips_panel_contents_when_centered_panel_is_closed(monkeypatch):
    ui = Mock()
    ui.begin_centered_panel.return_value = False
    monkeypatch.setattr(loading_module, "imgui", Mock())

    LoadingStatusPanel().render(
        ui, SimpleNamespace(progress=0.0, status_text="Waiting"), None,
        (1280, 720), Mock(),
    )

    ui.draw_title.assert_not_called()
    ui.draw_progress_bar.assert_not_called()
    ui.end_panel.assert_not_called()
