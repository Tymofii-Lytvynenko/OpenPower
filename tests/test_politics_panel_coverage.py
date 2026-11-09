from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.panels.politics_panel as politics_module
from src.client.ui.panels.politics_panel import PoliticsPanel


def summary():
    return SimpleNamespace(
        government_type="Republic",
        capital_name="Capital City",
        ideology_balance=0.4,
        approval_pct=70.0,
        stability_pct=55.0,
        corruption_pct=20.0,
        active_treaties=3,
        pending_treaties=2,
    )


class Ui:
    def __init__(self, clicked=()):
        self.clicked = set(clicked)
        self.buttons = []
        self.texts = []
        self.meters = []

    def text(self, *args, **kwargs):
        self.texts.append((args, kwargs))

    def meter(self, *args, **kwargs):
        self.meters.append((args, kwargs))

    def button(self, _slot, _label, test_id, *, enabled=True, **kwargs):
        self.buttons.append((test_id, enabled, kwargs))
        return enabled and test_id in self.clicked


def install_panel(monkeypatch, ui):
    monkeypatch.setattr(politics_module, "GMLWidgets", lambda _root: ui)
    panel = PoliticsPanel()
    panel._presenter = Mock()
    panel._presenter.build_summary.return_value = summary()
    return panel


def test_render_content_draws_summary_and_dispatches_available_navigation(monkeypatch):
    ui = Ui({"politics.open_constitution", "politics.open_laws", "politics.open_treaties"})
    panel = install_panel(monkeypatch, ui)
    open_constitution = Mock()
    open_laws = Mock()
    open_treaties = Mock()
    panel._open_constitution_cb = open_constitution
    panel._open_laws_cb = open_laws
    panel._open_treaties_cb = open_treaties

    panel._render_content(SimpleNamespace(), "USA", True)

    open_constitution.assert_called_once_with()
    open_laws.assert_called_once_with()
    open_treaties.assert_called_once_with()
    assert [row[0] for row in ui.buttons] == [
        "politics.open_constitution", "politics.open_laws", "politics.open_treaties",
    ]
    assert all(row[1] for row in ui.buttons)
    assert any(args[0] == "frmPressure/txtValue" for args, _ in ui.texts)
    assert any(args[0] == "frmPressure/frmGradient" for args, _ in ui.meters)
    assert ui.buttons[-1][2]["tooltip"] == "Active treaties: 3\nPending proposals: 2"


def test_render_content_disables_navigation_for_missing_callbacks_or_foreign_country(monkeypatch):
    ui = Ui({"politics.open_constitution", "politics.open_laws", "politics.open_treaties"})
    panel = install_panel(monkeypatch, ui)

    panel._render_content(SimpleNamespace(), "CAN", False)

    assert [enabled for _test_id, enabled, _kwargs in ui.buttons] == [False, False, False]
    assert ui.buttons[-1][2]["tooltip"] == "Active treaties: 3\nPending proposals: 2"


def test_render_respects_window_open_state_and_uses_the_politics_pillar_position(monkeypatch):
    is_open = False
    windows = []

    @contextmanager
    def window(title, **kwargs):
        windows.append((title, kwargs))
        yield is_open

    monkeypatch.setattr(politics_module.WindowManager, "window", window)
    monkeypatch.setattr(politics_module, "main_pillar_position", lambda _name: (12, 34))
    monkeypatch.setattr(politics_module, "imgui", SimpleNamespace(
        WindowFlags_=SimpleNamespace(no_resize=1, no_scrollbar=2, no_scroll_with_mouse=4)
    ))
    panel = PoliticsPanel()
    panel._render_content = Mock()
    state = SimpleNamespace()
    context = SimpleNamespace(target_tag="USA", is_own_country=True)

    assert panel.render(state, context) is False
    is_open = True
    assert panel.render(state, context) is True

    assert windows[0] == ("POLITICS", {
        "x": 12, "y": 34, "w": 240, "h": 520, "test_id": "politics.panel", "flags": 7,
    })
    panel._render_content.assert_called_once_with(state, context.target_tag, context.is_own_country)
