from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from imgui_bundle import imgui

from src.client.ui.components.hud import system_bar as system_bar_module
from src.client.ui.components.hud.system_bar import SystemBar


class FakeSlide:
    def __init__(self, *, value=0.0, active=False):
        self.value = value
        self.active = active
        self.calls = []

    def snap(self, target):
        self.calls.append(("snap", target))
        self.value = target
        self.active = False

    def advance(self, now):
        self.calls.append(("advance", now))

    def begin(self, target, now):
        self.calls.append(("begin", target, now))
        self.active = True


class FakeWidgets:
    def __init__(self, template, calls=None):
        self.template = template
        self.calls = calls if calls is not None else []

    def frame(self, label):
        self.calls.append(("frame", label))

    def toggle(self, *args, **kwargs):
        return False, True

    def button(self, *args, **kwargs):
        self.calls.append(("button", args, kwargs))
        return args[0] != "btnF2"

    def text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))


def imgui_stub(**overrides):
    values = {
        "Key": SimpleNamespace(f1=1, f3=3, f4=4, f5=5, f6=6, f9=9, f10=10),
        "Cond_": SimpleNamespace(always=1),
        "WindowFlags_": SimpleNamespace(
            no_decoration=1, no_move=2, no_saved_settings=4, no_scroll_with_mouse=8, no_background=16
        ),
        "StyleVar_": SimpleNamespace(window_padding=1),
        "get_main_viewport": lambda: SimpleNamespace(
            pos=SimpleNamespace(x=100.0, y=20.0), size=SimpleNamespace(x=400.0, y=600.0)
        ),
        "get_time": lambda: 12.5,
        "set_next_window_pos": lambda *_args: None,
        "set_next_window_size": lambda *_args: None,
        "push_style_var": lambda *_args: None,
        "pop_style_var": lambda: None,
        "begin": lambda *_args, **_kwargs: (True, True),
        "get_window_pos": lambda: SimpleNamespace(x=50.0, y=20.0),
        "get_style": lambda: SimpleNamespace(font_scale_main=1.0, font_scale_dpi=1.0),
        "push_font": lambda *_args: None,
        "pop_font": lambda: None,
        "end": lambda: None,
        "is_key_pressed": lambda *_args: False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_consume_shortcuts_dispatches_only_pressed_keys(monkeypatch):
    calls = []
    pressed = set()
    monkeypatch.setattr(
        system_bar_module,
        "imgui",
        imgui_stub(is_key_pressed=lambda key, repeat: key in pressed),
    )
    bar = SystemBar(
        open_help_cb=lambda: calls.append("help"),
        open_objectives_cb=lambda: calls.append("objectives"),
        open_console_cb=lambda: calls.append("console"),
        open_history_cb=lambda: calls.append("history"),
        open_menu_cb=lambda: calls.append("menu"),
        open_save_cb=lambda: calls.append("save"),
        open_load_cb=lambda: calls.append("load"),
    )

    bar._consume_shortcuts(None, None)
    assert calls == []

    pressed.update({1, 3, 4, 5, 6, 9, 10})
    bar._consume_shortcuts(None, None)

    assert calls == ["help", "save", "load", "objectives", "history", "console", "menu"]


def test_render_toggle_begins_slide_only_when_state_changes(monkeypatch):
    monkeypatch.setattr(system_bar_module, "imgui", imgui_stub())
    bar = SystemBar()
    bar._expanded_width = 500.0
    bar._collapsed_width = 36.0
    bar._slide = FakeSlide()

    assert bar._render_toggle(SimpleNamespace(toggle=lambda *args, **kwargs: (True, False))) is True
    assert bar._expanded is False
    assert bar._slide.calls == [("begin", 36.0, 12.5)]

    bar._slide.calls.clear()
    assert bar._render_toggle(SimpleNamespace(toggle=lambda *args, **kwargs: (False, True))) is False
    assert bar._expanded is True
    assert bar._slide.calls == []


def test_render_shortcuts_dispatches_enabled_actions_and_restores_font(monkeypatch):
    calls = []
    monkeypatch.setattr(
        system_bar_module,
        "imgui",
        imgui_stub(
            get_style=lambda: SimpleNamespace(font_scale_main=0.05, font_scale_dpi=1.0),
            push_font=lambda font, size: calls.append(("push_font", font, size)),
            pop_font=lambda: calls.append(("pop_font",)),
        ),
    )
    bar = SystemBar(
        open_help_cb=lambda: calls.append("help"),
        open_objectives_cb=lambda: calls.append("objectives"),
        open_menu_cb=lambda: calls.append("menu"),
        open_save_cb=lambda: calls.append("save"),
        open_load_cb=lambda: calls.append("load"),
    )
    ui = FakeWidgets("template", calls)

    bar._render_shortcuts(ui, net_client=object(), nav_service=object())

    buttons = [event for event in calls if isinstance(event, tuple) and event[0] == "button"]
    assert len(buttons) == 6
    assert [event[2]["enabled"] for event in buttons] == [True, False, True, True, True, True]
    assert [event[2]["dynamic_enabled"] for event in buttons] == [True] * 6
    assert calls.count(("push_font", None, 100.0)) == 6
    assert calls.count(("pop_font",)) == 6
    assert all(event[2]["test_id"].startswith("hud.system.") for event in calls if event[0] == "text")
    assert [
        event
        for event in calls
        if isinstance(event, str) and event in {"help", "save", "load", "objectives", "menu"}
    ] == [
        "help", "save", "load", "objectives", "menu"
    ]


def test_render_shortcuts_pops_font_when_text_rendering_raises(monkeypatch):
    calls = []
    monkeypatch.setattr(system_bar_module, "imgui", imgui_stub(push_font=lambda *_args: None, pop_font=lambda: calls.append("pop")))
    bar = SystemBar()
    ui = SimpleNamespace(
        button=lambda *_args, **_kwargs: False,
        text=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("text failed")),
    )

    with pytest.raises(RuntimeError, match="text failed"):
        bar._render_shortcuts(ui, None, None)

    assert calls == ["pop"]


def test_render_uses_viewport_clamps_width_and_ends_closed_windows(monkeypatch):
    calls = []
    monkeypatch.setattr(
        system_bar_module,
        "imgui",
        imgui_stub(
            begin=lambda *args, **kwargs: (False, False),
            set_next_window_pos=lambda *args: calls.append(("pos", args)),
            set_next_window_size=lambda *args: calls.append(("size", args)),
            pop_style_var=lambda: calls.append("pop"),
            end=lambda: calls.append("end"),
        ),
    )
    layout = SimpleNamespace(width=577.0, height=38.0)
    monkeypatch.setattr(system_bar_module, "get_gml_layout", lambda _template: layout)
    monkeypatch.setattr(system_bar_module, "gml_style", nullcontext)
    bar = SystemBar()
    bar._consume_shortcuts = lambda *_args: calls.append("consume")
    bar._render_toggle = lambda _ui: False
    bar._render_shortcuts = lambda *_args: calls.append("shortcuts")

    bar.render(None, None)

    assert bar._expanded_width == 400.0
    assert bar._collapsed_width == 36.0
    assert bar._slide.value == 400.0
    assert ("pos", ((100.0, 20.0), 1)) in calls
    assert ("size", ((400.0, 38.0), 1)) in calls
    assert calls[-2:] == ["pop", "end"]
    assert "shortcuts" not in calls


@pytest.mark.parametrize(
    "opened, toggle_changed, expanded, slide_active, expected_shortcuts",
    [
        (True, True, True, False, False),
        (True, False, False, False, False),
        (True, False, False, True, True),
    ],
)
def test_render_routes_visible_content_by_toggle_and_transition_state(
    monkeypatch, opened, toggle_changed, expanded, slide_active, expected_shortcuts
):
    calls = []
    monkeypatch.setattr(system_bar_module, "imgui", imgui_stub(begin=lambda *args, **kwargs: (opened, True)))
    monkeypatch.setattr(system_bar_module, "get_gml_layout", lambda _template: SimpleNamespace(width=500, height=38))
    monkeypatch.setattr(system_bar_module, "gml_style", nullcontext)
    monkeypatch.setattr(system_bar_module, "create_gml_layout_session", lambda *args: "session")
    monkeypatch.setattr(system_bar_module, "use_gml_layout", lambda _session: nullcontext())
    monkeypatch.setattr(system_bar_module, "GMLWidgets", lambda _template: FakeWidgets("template"))
    bar = SystemBar()
    bar._expanded = expanded
    bar._slide = FakeSlide(value=400, active=slide_active)
    bar._slide_initialized = True
    bar._consume_shortcuts = lambda *_args: None
    bar._render_toggle = lambda _ui: toggle_changed
    bar._render_shortcuts = lambda *_args: calls.append("shortcuts")

    bar.render(None, None)

    assert ("shortcuts" in calls) is expected_shortcuts


def test_show_save_load_and_menu_choose_callbacks_or_navigation_routes():
    calls = []
    bar = SystemBar(
        open_menu_cb=lambda: calls.append("menu-callback"),
        open_save_cb=lambda: calls.append("save-callback"),
        open_load_cb=lambda: calls.append("load-callback"),
    )
    nav = SimpleNamespace(
        show_load_game_screen=lambda config: calls.append(("load-route", config)),
        show_main_menu=lambda session, config: calls.append(("menu-route", session, config)),
    )
    net = SimpleNamespace(request_save=lambda: calls.append("save-request"), session="session")
    nav.window = SimpleNamespace(game_config="config")

    bar._show_save(net)
    bar._show_load(nav, net)
    bar._toggle_menu(nav, net)
    assert calls == ["save-callback", "load-callback", "menu-callback"]

    fallback = SystemBar()
    fallback._show_save(net)
    fallback._show_load(nav, net)
    fallback._show_menu(nav, net)
    assert calls[-3:] == ["save-request", ("load-route", "config"), ("menu-route", "session", "config")]


def test_menu_load_routes_require_both_session_and_window_config():
    calls = []
    bar = SystemBar()
    nav = SimpleNamespace(window=SimpleNamespace(game_config="config"), show_main_menu=lambda *args: calls.append(args))
    no_session = SimpleNamespace()

    assert bar._resolve_session_and_config(nav, no_session) == (None, None)
    assert bar._resolve_session_and_config(SimpleNamespace(window=SimpleNamespace()), SimpleNamespace(session="session")) == (None, None)
    assert bar._resolve_session_and_config(nav, SimpleNamespace(session="session")) == ("session", "config")
    bar._show_menu(nav, no_session)
    bar._show_load(nav, no_session)
    assert calls == []
    bar._show_menu(nav, SimpleNamespace(session="session"))
    assert calls == [("session", "config")]


def test_toggle_menu_uses_route_when_no_callback_is_configured():
    calls = []
    bar = SystemBar()
    bar._show_menu = lambda nav, net: calls.append((nav, net))

    bar._toggle_menu("nav", "net")

    assert calls == [("nav", "net")]


def test_safe_call_ignores_missing_callbacks():
    calls = []
    bar = SystemBar()

    bar._safe_call(None)
    bar._safe_call(lambda: calls.append("called"))

    assert calls == ["called"]
