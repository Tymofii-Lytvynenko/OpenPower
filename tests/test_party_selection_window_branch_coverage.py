from contextlib import contextmanager
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

from src.client.ui.components.shared.party_selection_window import PartySelectionWindow


class _FakeImgui:
    Col_ = SimpleNamespace(window_bg=1)

    def __init__(self, *, list_open=True, selected=()):
        self.list_open = list_open
        self.selected = set(selected)
        self.calls = []

    def push_style_color(self, *args):
        self.calls.append(("push_style_color", args))

    def pop_style_color(self):
        self.calls.append(("pop_style_color",))

    def begin_child(self, *args, **kwargs):
        self.calls.append(("begin_child", args, kwargs))
        return self.list_open

    def end_child(self):
        self.calls.append(("end_child",))

    def selectable(self, label, selected, *, test_id, gml_id):
        self.calls.append(("selectable", label, selected, test_id, gml_id))
        return (test_id in self.selected,)

    def same_line(self, offset):
        self.calls.append(("same_line", offset))

    def text(self, value):
        self.calls.append(("text", value))

    def text_disabled(self, value):
        self.calls.append(("text_disabled", value))


class _FakeWidgets:
    def __init__(self, template, buttons=()):
        self.template = template
        self.buttons = set(buttons)
        self.calls = []

    def path(self, source_path):
        self.calls.append(("path", source_path))
        return f"gml:{source_path}"

    def button(self, source_path, label, test_id, **kwargs):
        self.calls.append(("button", source_path, label, test_id, kwargs))
        return test_id in self.buttons


def _state(**tables):
    return SimpleNamespace(tables=tables)


def _install_ui(monkeypatch, *, imgui, window_open=True, buttons=()):
    module = import_module("src.client.ui.components.shared.party_selection_window")
    widgets = _FakeWidgets("Party_Selection_Window", buttons)
    window_calls = []

    @contextmanager
    def window(*args, **kwargs):
        window_calls.append((args, kwargs))
        yield window_open

    monkeypatch.setattr(module, "imgui", imgui)
    monkeypatch.setattr(module, "WindowManager", SimpleNamespace(window=window))
    monkeypatch.setattr(module, "GMLWidgets", lambda template: widgets)
    monkeypatch.setattr(
        module,
        "GAMETHEME",
        SimpleNamespace(colors=SimpleNamespace(bg_popup="popup-bg")),
    )
    return widgets, window_calls


def test_party_options_filter_normalize_and_sort_rows():
    assert PartySelectionWindow.party_options(_state(), "USA") == []
    assert PartySelectionWindow.party_options(
        _state(political_parties=pl.DataFrame({"party_id": ["P"]})), "USA",
    ) == []

    state = _state(
        political_parties=pl.DataFrame(
            {
                "country_id": [" usa ", "USA", "USA", "CAN", "USA"],
                "party_id": ["Beta", "zeta", "", "North", "alpha"],
                "support_share": [0.1, 0.3, 0.9, 1.0, float("nan")],
            }
        )
    )

    options = PartySelectionWindow.party_options(state, " usa ")

    assert [row["party_id"] for row in options] == ["zeta", "Beta", "alpha"]


def test_default_party_prefers_ruling_party_then_highest_support():
    state = _state(
        political_parties=pl.DataFrame(
            {
                "country_id": ["USA", "USA", "USA"],
                "party_id": ["Alpha", "Beta", "Gamma"],
                "support_share": [0.2, 0.6, 0.2],
            }
        ),
        country_governments=pl.DataFrame(
            {"country_id": ["usa"], "ruling_party_id": [" alpha "]}
        ),
    )

    assert PartySelectionWindow.default_party_id(state, "USA") == "Alpha"
    assert PartySelectionWindow.default_party_id(
        _state(political_parties=state.tables["political_parties"]), "USA",
    ) == "Beta"
    assert PartySelectionWindow.default_party_id(
        _state(
            political_parties=pl.DataFrame(
                {"country_id": ["USA"], "party_id": ["Solo"]}
            ),
            country_governments=pl.DataFrame({"country_id": ["USA"], "other": ["x"]}),
        ),
        "USA",
    ) == "Solo"
    assert PartySelectionWindow.default_party_id(_state(), "USA") == ""


def test_show_validates_selection_and_closed_render_is_a_noop(monkeypatch):
    imgui = _FakeImgui()
    _install_ui(monkeypatch, imgui=imgui)
    callback = Mock()
    window = PartySelectionWindow(callback)
    state = _state(
        political_parties=pl.DataFrame(
            {"country_id": ["USA", "USA"], "party_id": ["A", "B"]}
        )
    )

    assert not window.is_open
    window.render(1280, 720)
    assert imgui.calls == []

    window.show(state, " usa ", "B")
    assert window.is_open
    assert window._country_id == "USA"
    assert window._selected_party_id == "B"

    window.show(state, "USA", "missing")
    assert window._selected_party_id == "A"


def test_render_lists_parties_and_confirms_selection(monkeypatch):
    imgui = _FakeImgui(selected={"new_game.party_selection.party.B"})
    widgets, window_calls = _install_ui(
        monkeypatch,
        imgui=imgui,
        buttons={"new_game.party_selection.confirm"},
    )
    callback = Mock()
    window = PartySelectionWindow(callback)
    window.show(
        _state(
            political_parties=pl.DataFrame(
                {
                    "country_id": ["USA", "USA"],
                    "party_id": ["A", "B"],
                    "display_name": ["Alpha Party", "Beta Party"],
                    "support_share": [0.125, 0.4],
                }
            )
        ),
        "USA",
        "B",
    )

    window.render(1280, 720)

    assert callback.call_args.args == ("B",)
    assert not window.is_open
    assert imgui.calls[0][0] == "push_style_color"
    assert imgui.calls[-1] == ("pop_style_color",)
    assert [call[1] for call in imgui.calls if call[0] == "text"] == ["40.0 %", "12.5 %"]
    assert any(call[0] == "selectable" and call[2] for call in imgui.calls)
    assert any(call[0] == "end_child" for call in imgui.calls)
    assert window_calls[0][1]["test_id"] == "new_game.party_selection.dialog"
    assert any(call[0] == "button" and call[3] == "new_game.party_selection.confirm" for call in widgets.calls)


def test_empty_and_closed_lists_and_window_cancel_paths(monkeypatch):
    imgui = _FakeImgui(list_open=True)
    _install_ui(
        monkeypatch,
        imgui=imgui,
        buttons={"new_game.party_selection.cancel"},
    )
    window = PartySelectionWindow(Mock())
    window.show(_state(), "USA")

    window.render(800, 600)

    assert not window.is_open
    assert ("text_disabled", "No political-party data available.") in imgui.calls
    assert imgui.calls.count(("end_child",)) == 1

    closed_imgui = _FakeImgui(list_open=False)
    _install_ui(monkeypatch, imgui=closed_imgui, window_open=False)
    closed_window = PartySelectionWindow(Mock())
    closed_window.show(_state(), "USA")

    closed_window.render(800, 600)

    assert not closed_window.is_open
    assert not any(call[0] == "begin_child" for call in closed_imgui.calls)
    assert closed_imgui.calls[-1] == ("pop_style_color",)


def test_finite_number_handles_bad_and_non_finite_values():
    module = import_module("src.client.ui.components.shared.party_selection_window")

    assert module._finite_number("2.5") == 2.5
    assert module._finite_number("not-a-number") == 0.0
    assert module._finite_number(None) == 0.0
    assert module._finite_number(float("nan")) == 0.0
    assert module._finite_number(float("inf")) == 0.0
