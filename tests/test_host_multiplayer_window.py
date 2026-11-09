from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.client.ui.components.shared import host_multiplayer_window as host_module


class _Widgets:
    def __init__(self, *, clicked=(), combo_results=(), toggle_results=()):
        self.clicked = set(clicked)
        self.combo_results = iter(combo_results)
        self.toggle_results = iter(toggle_results)
        self.frames = []
        self.text_calls = []
        self.combos = []
        self.toggles = []
        self.buttons = []

    def frame(self, slot):
        self.frames.append(slot)

    def text(self, slot, value, **kwargs):
        self.text_calls.append((slot, value, kwargs))

    def path(self, slot):
        return f"Host_Multiplayer_Game/{slot}"

    def toggle(self, slot, value, test_id, **kwargs):
        self.toggles.append((slot, value, test_id, kwargs))
        return next(self.toggle_results, (False, value))

    def combo_at(self, *args, **kwargs):
        self.combos.append((args, kwargs))
        return next(self.combo_results, (False, args[2]))

    def button(self, slot, label, test_id, *, enabled=True, **kwargs):
        self.buttons.append((slot, label, test_id, enabled, kwargs))
        return enabled and test_id in self.clicked


def _imgui(monkeypatch):
    native = Mock()
    native.WindowFlags_ = SimpleNamespace(
        no_resize=1,
        no_collapse=2,
        no_scrollbar=4,
        no_scroll_with_mouse=8,
    )
    native.InputTextFlags_ = SimpleNamespace(password=16)
    native.input_text.side_effect = [
        (True, "War Room"),
        (True, "secret"),
        (True, "12"),
        (True, "5566"),
        (True, "90"),
    ]
    monkeypatch.setattr(host_module, "imgui", native)
    return native


def test_show_and_close_normalize_mode_and_keep_each_draft_independent():
    cancelled = Mock()
    window = host_module.HostMultiplayerGameWindow(cancelled)

    window.close()
    assert cancelled.call_count == 0
    window.show("LaN")
    assert window.is_open is True
    assert window.mode == "lan"
    window.draft.objectives[0].enabled = True
    window.close()
    window.close()
    assert window.is_open is False
    assert cancelled.call_count == 1

    window.show("unsupported")
    assert window.mode == "internet"
    assert host_module.HostMultiplayerGameWindow(Mock()).draft.objectives[0].enabled is False


def test_render_updates_host_draft_and_cancel_uses_the_shared_close_path(monkeypatch):
    native = _imgui(monkeypatch)
    widgets = _Widgets(
        clicked={"multiplayer.host.cancel", "multiplayer.host.start"},
        combo_results=[(True, 4), (True, 1), (True, 2)],
        toggle_results=[(True, True), (True, True)],
    )
    monkeypatch.setattr(host_module, "GMLWidgets", lambda _root: widgets)
    cancelled = Mock()
    window = host_module.HostMultiplayerGameWindow(cancelled)
    window.show("lan")

    with patch.object(
        host_module.WindowManager,
        "window",
        return_value=nullcontext(True),
    ) as begin:
        window.render(900, 700)

    begin.assert_called_once()
    assert begin.call_args.args == ("HOST MULTIPLAYER GAME",)
    assert begin.call_args.kwargs["x"] == 279.5
    assert begin.call_args.kwargs["y"] == 179.0
    assert begin.call_args.kwargs["flags"] == 15
    assert len(widgets.frames) == 9
    assert window.draft.server_name == "War Room"
    assert window.draft.password == "secret"
    assert (window.draft.max_players, window.draft.port, window.draft.time_limit) == (
        "12",
        "5566",
        "90",
    )
    assert window.draft.dedicated_server is True
    assert (window.draft.game_speed_index, window.draft.nuclear_option_index) == (4, 1)
    assert window.draft.objectives[0].enabled is True
    assert window.draft.objectives[0].time_limit_index == 2
    assert all(not button[3] for button in widgets.buttons if button[2] == "multiplayer.host.start")
    assert cancelled.call_count == 1
    assert window.is_open is False
    assert native.input_text.call_args_list[1].args[2] == 16


def test_render_is_idle_when_hidden_and_closes_when_window_manager_closes_it(monkeypatch):
    _imgui(monkeypatch)
    widgets = _Widgets()
    monkeypatch.setattr(host_module, "GMLWidgets", lambda _root: widgets)
    cancelled = Mock()
    window = host_module.HostMultiplayerGameWindow(cancelled)
    begin = Mock(return_value=nullcontext(False))

    with patch.object(host_module.WindowManager, "window", begin):
        window.render(800, 600)
        window.show("internet")
        window.render(800, 600)

    assert begin.call_count == 1
    assert widgets.frames == []
    assert cancelled.call_count == 1
    assert window.is_open is False


def test_render_content_returns_when_disabled_start_button_reports_clicked(monkeypatch):
    widgets = Mock()
    widgets.button.return_value = True
    monkeypatch.setattr(host_module, "GMLWidgets", lambda _root: widgets)
    cancelled = Mock()
    window = host_module.HostMultiplayerGameWindow(cancelled)
    window._render_server_identity = Mock()
    window._render_server_settings = Mock()
    window._render_game_settings = Mock()
    window._render_objectives = Mock()

    window._render_content()

    widgets.button.assert_called_once_with(
        "frmInner/btnStart",
        "START GAME",
        "multiplayer.host.start",
        enabled=False,
        tooltip="OpenPower has no authoritative multiplayer host service.",
    )
    cancelled.assert_not_called()
