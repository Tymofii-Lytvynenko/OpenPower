from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

from src.client.ui.components.shared import multiplayer_windows as windows_module
from src.client.ui.components.shared.multiplayer_windows import (
    GenericInputDialog,
    JoinMultiplayerWindow,
    MultiplayerServerInfo,
    ServerInfoWindow,
)


class FakeWidgets:
    results = {}
    calls = []
    rect_result = None

    def __init__(self, root):
        self.root = root

    def text(self, slot, value, **kwargs):
        self.calls.append(("text", self.root, slot, value, kwargs))

    def text_at(self, slot, value, **kwargs):
        self.calls.append(("text_at", self.root, slot, value, kwargs))

    def path(self, slot):
        return f"{self.root}/{slot}"

    def button(self, slot, label, test_id, *, enabled=True, **kwargs):
        self.calls.append(("button", self.root, slot, label, test_id, enabled, kwargs))
        return bool(enabled and self.results.get(test_id, False))

    def button_at(self, slot, label, test_id, **kwargs):
        enabled = kwargs.get("enabled", True)
        self.calls.append(("button_at", self.root, slot, label, test_id, kwargs))
        return bool(enabled and self.results.get(test_id, False))

    def rect(self, slot):
        self.calls.append(("rect", self.root, slot))
        return self.rect_result


def install_ui(monkeypatch, *, window_open=True, child_open=True, layout=None):
    imgui = Mock()
    imgui.WindowFlags_ = SimpleNamespace(
        no_title_bar=1,
        no_resize=2,
        no_move=4,
        no_collapse=8,
        no_scrollbar=16,
        no_scroll_with_mouse=32,
    )
    imgui.InputTextFlags_ = SimpleNamespace(none=0, password=1)
    imgui.input_text.return_value = (False, "")
    imgui.get_color_u32.side_effect = lambda color: tuple(color)
    imgui.get_window_draw_list.return_value = Mock()
    FakeWidgets.results = {}
    FakeWidgets.calls = []
    FakeWidgets.rect_result = None
    monkeypatch.setattr(windows_module, "imgui", imgui)
    monkeypatch.setattr(windows_module, "GMLWidgets", FakeWidgets)
    monkeypatch.setattr(windows_module, "active_gml_layout", lambda: layout)

    @contextmanager
    def window(*_args, **_kwargs):
        yield window_open

    @contextmanager
    def child_frame(*_args, **_kwargs):
        yield child_open

    monkeypatch.setattr(windows_module.WindowManager, "window", staticmethod(window))
    monkeypatch.setattr(windows_module, "gml_child_frame", child_frame)
    return imgui


def test_generic_input_dialog_normalizes_requests_and_acknowledges_once():
    dialog = GenericInputDialog()
    submitted = []
    cancelled = Mock()

    assert dialog.show("  ", submitted.append) is False
    assert dialog.show(None, submitted.append) is False
    assert dialog.show(
        "  Enter password  ", submitted.append, cancelled,
        initial_value=123, password=1,
    ) is True
    assert dialog.is_open is True
    assert dialog._request.message == "Enter password"
    assert dialog._request.initial_value == "123"
    assert dialog._request.password is True
    assert dialog._value == "123"
    assert dialog._focus_requested is True
    assert dialog.show("Another request", submitted.append) is False

    dialog.close(submit=True)
    assert submitted == ["123"]
    assert dialog.is_open is False
    assert dialog._value == ""
    assert dialog._focus_requested is False
    dialog.close(submit=False)
    cancelled.assert_not_called()

    assert dialog.show("Optional cancel", submitted.append) is True
    dialog._value = "draft"
    dialog.close(submit=False)
    cancelled.assert_not_called()
    assert dialog.show("Cancel me", submitted.append, cancelled) is True
    dialog._value = "discarded"
    dialog.close(submit=False)
    cancelled.assert_called_once_with()
    assert submitted == ["123"]


def test_generic_input_dialog_render_handles_focus_password_submit_and_cancel(monkeypatch):
    imgui = install_ui(monkeypatch)
    submitted = Mock()
    cancelled = Mock()
    dialog = GenericInputDialog()

    assert dialog.render(900, 700) is False
    assert dialog.show("Password", submitted, cancelled, initial_value="seed", password=True)
    imgui.input_text.return_value = (False, "seed")
    assert dialog.render(900, 700) is True
    imgui.set_keyboard_focus_here.assert_called_once_with()
    assert imgui.input_text.call_args.args[2] == imgui.InputTextFlags_.password

    imgui.input_text.return_value = (True, "secret")
    FakeWidgets.results = {"multiplayer.input.ok": True}
    assert dialog.render(900, 700) is False
    submitted.assert_called_once_with("secret")
    cancelled.assert_not_called()
    assert imgui.set_keyboard_focus_here.call_count == 1

    assert dialog.show("Text", submitted, cancelled)
    imgui.input_text.return_value = (False, "draft")
    FakeWidgets.results = {"multiplayer.input.cancel": True}
    assert dialog.render(900, 700) is False
    assert imgui.input_text.call_args.args[2] == imgui.InputTextFlags_.none
    cancelled.assert_called_once_with()


def test_generic_input_dialog_stays_open_when_native_window_is_closed(monkeypatch):
    install_ui(monkeypatch, window_open=False)
    dialog = GenericInputDialog()
    assert dialog.show("Still pending", Mock())

    assert dialog.render(800, 600) is True
    assert dialog.is_open is True


def test_server_info_window_renders_unavailable_and_server_details(monkeypatch):
    imgui = install_ui(monkeypatch)
    window = ServerInfoWindow()

    assert window.render(900, 700) is False
    window.show(None)
    assert window.is_open is True
    assert window.render(900, 700) is True
    assert any(
        call[0] == "text" and call[2] == "frmInner/frmInfo/txtName" and call[3] == "Unavailable"
        for call in FakeWidgets.calls
    )
    assert any(
        call[0] == "button" and call[4] == "multiplayer.server_info.join" and not call[5]
        for call in FakeWidgets.calls
    )
    imgui.get_window_draw_list.assert_not_called()

    layout = SimpleNamespace(window_position=(10.0, 20.0))
    install_ui(monkeypatch, layout=layout)
    imgui = windows_module.imgui
    slot = SimpleNamespace(x=3.0, y=4.0, width=12.0, height=8.0)
    FakeWidgets.rect_result = slot
    joined = Mock()
    server_without_password = MultiplayerServerInfo(
        "Local host", "127.0.0.1", 2, 8, "Base", "Sandbox",
    )
    window.show(server_without_password)

    assert window.render(900, 700) is True
    draw_list = imgui.get_window_draw_list.return_value
    draw_list.add_rect.assert_called_once()
    draw_list.add_rect_filled.assert_not_called()
    assert any(
        call[0] == "button" and call[4] == "multiplayer.server_info.join" and not call[5]
        for call in FakeWidgets.calls
    )

    FakeWidgets.calls = []
    draw_list.add_rect.reset_mock()
    draw_list.add_rect_filled.reset_mock()
    server = MultiplayerServerInfo(
        "Local host", "127.0.0.1", 2, 8, "Base", "Sandbox", password_required=True,
    )
    window.show(server, joined)
    FakeWidgets.results = {"multiplayer.server_info.join": True}

    assert window.render(900, 700) is False
    joined.assert_called_once_with()
    assert window.is_open is False
    imgui = windows_module.imgui
    draw_list = imgui.get_window_draw_list.return_value
    draw_list.add_rect.assert_called_once()
    draw_list.add_rect_filled.assert_called_once()
    assert any(
        call[0] == "text" and call[2] == "frmInner/frmInfo/txtPlayers" and call[3] == "2/8"
        for call in FakeWidgets.calls
    )


def test_server_info_window_without_join_callback_and_native_close_cleans_state(monkeypatch):
    imgui = install_ui(monkeypatch, window_open=False)
    window = ServerInfoWindow()
    server = MultiplayerServerInfo("Host", "10.0.0.1", 1, 4, "Mod", "Scenario")
    window.show(server)

    assert window.render(900, 700) is False
    assert window.is_open is False
    assert window._server is None
    assert window._on_join is None
    imgui.get_window_draw_list.assert_not_called()


def test_join_window_normalizes_mode_renders_geometry_and_delegates_host(monkeypatch):
    layout = Mock()
    imgui = install_ui(monkeypatch, layout=layout)
    cancelled = Mock()
    loaded = Mock()
    hosted = Mock()
    window = JoinMultiplayerWindow(cancelled, loaded, hosted)

    window.render(900, 700)
    assert window.show(" LaN ") is None
    assert window._mode == "internet"
    window._selected_server = MultiplayerServerInfo("stale", "", 0, 0, "", "")
    window.show("LAN")
    assert window._mode == "lan"
    assert window._selected_server is None
    window.show("Internet")
    assert window._mode == "internet"

    FakeWidgets.results = {"multiplayer.join.host": True}
    window.render(900, 700)

    hosted.assert_called_once_with("internet")
    assert window.is_open is True
    assert layout.resize_component.call_args_list == [
        (("Join_Multiplayer_Game/frmInner",), {"height": 421.0}),
        (("Join_Multiplayer_Game/picWhiteBar",), {"height": 447.0}),
    ]
    assert imgui.text_wrapped.called
    assert any(call[0] == "text_at" for call in FakeWidgets.calls)

    layout.resize_component.reset_mock()
    monkeypatch.setattr(windows_module, "active_gml_layout", lambda: None)
    window._apply_source_runtime_geometry()
    layout.resize_component.assert_not_called()


def test_join_window_lan_controls_child_visibility_cancel_and_load_callbacks(monkeypatch):
    imgui = install_ui(monkeypatch, child_open=False)
    cancelled = Mock()
    loaded = Mock()
    window = JoinMultiplayerWindow(cancelled, loaded)
    window.show("lan")
    FakeWidgets.results = {"multiplayer.join.load_game": True}

    window._render_content()

    loaded.assert_called_once_with()
    assert window.is_open is True
    assert not imgui.text_wrapped.called
    assert any(
        call[0] == "button_at" and call[3] == "UPDATE" and call[5]["enabled"] is False
        for call in FakeWidgets.calls
    )
    assert any("/Tab2/" in call[2] for call in FakeWidgets.calls if call[0] == "text")

    FakeWidgets.results = {"multiplayer.join.cancel": True}
    window.render(800, 600)
    assert window.is_open is False
    cancelled.assert_called_once_with()


def test_join_window_optional_host_action_and_native_window_visibility(monkeypatch):
    imgui = install_ui(monkeypatch, child_open=False)
    window = JoinMultiplayerWindow(Mock())
    window.show("internet")

    window.render(800, 600)

    assert window.is_open is True
    imgui.text_wrapped.assert_not_called()
    assert any(call[0] == "text" and "/Tab1/" in call[2] for call in FakeWidgets.calls)


def test_join_window_closed_native_state_and_close_callback(monkeypatch):
    install_ui(monkeypatch)
    cancelled = Mock()
    window = JoinMultiplayerWindow(cancelled)
    window._selected_server = MultiplayerServerInfo("stale", "", 0, 0, "", "")

    window.close()

    assert window.is_open is False
    assert window._selected_server is None
    cancelled.assert_called_once_with()
