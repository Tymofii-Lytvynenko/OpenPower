from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from src.client.ui.components.shared import save_game_dialog as save_game_dialog_module


class _ImguiStub:
    def __init__(self, *, selections=(), hovered=(), input_value=None, button_clicked=False):
        self.selections = iter(selections)
        self.hovered = iter(hovered)
        self.input_value = input_value
        self.button_clicked = button_clicked
        self.cursor_x = 0.0
        self.calls = []

    def get_io(self):
        return SimpleNamespace(display_size=SimpleNamespace(x=1280, y=720))

    def text_disabled(self, text):
        self.calls.append(("text_disabled", text))

    def set_cursor_pos_x(self, value):
        self.cursor_x = value

    def get_cursor_pos_x(self):
        return self.cursor_x

    def selectable(self, label, selected, *, size, test_id):
        clicked = next(self.selections, False)
        self.calls.append(("selectable", label, selected, size, test_id, clicked))
        return clicked, False

    def is_item_hovered(self):
        return next(self.hovered, False)

    def set_tooltip(self, text):
        self.calls.append(("tooltip", text))

    def same_line(self, offset):
        self.calls.append(("same_line", offset))

    def input_text(self, label, value, **kwargs):
        self.calls.append(("input_text", label, value, kwargs))
        if self.input_value is None:
            return False, value
        return True, self.input_value


class _WidgetsStub:
    def __init__(self, root, calls, *, button_clicked=False):
        self.root = root
        self.calls = calls
        self.button_clicked = button_clicked

    def text(self, identifier, value):
        self.calls.append(("text", identifier, value))

    def path(self, identifier):
        return f"{self.root}/{identifier}"

    def button(self, identifier, label, test_id, *, enabled=True):
        self.calls.append(("button", identifier, label, test_id, enabled))
        return self.button_clicked and enabled


def _install_render_stubs(
    monkeypatch,
    *,
    window_open=True,
    list_open=True,
    selections=(),
    hovered=(),
    input_value=None,
    button_clicked=False,
):
    calls = {"window": [], "list": [], "widgets": []}
    imgui = _ImguiStub(
        selections=selections,
        hovered=hovered,
        input_value=input_value,
        button_clicked=button_clicked,
    )
    widgets = _WidgetsStub("", calls["widgets"], button_clicked=button_clicked)

    def window(*args, **kwargs):
        calls["window"].append((args, kwargs))
        return nullcontext(window_open)

    def child_frame(path, *, bordered):
        calls["list"].append((path, bordered))
        return nullcontext(list_open)

    monkeypatch.setattr(save_game_dialog_module, "imgui", imgui)
    monkeypatch.setattr(save_game_dialog_module.WindowManager, "window", window)
    monkeypatch.setattr(save_game_dialog_module, "gml_child_frame", child_frame)
    monkeypatch.setattr(
        save_game_dialog_module,
        "GMLWidgets",
        lambda root: _WidgetsStub(root, calls["widgets"], button_clicked=button_clicked),
    )
    monkeypatch.setattr(
        save_game_dialog_module.UIPrimitives,
        "fit_text",
        staticmethod(lambda value, width: f"{value}|{width:g}"),
    )
    return calls, imgui


def test_toggle_rejects_unknown_mode_and_toggling_current_mode_closes(monkeypatch):
    listed = []
    dialog = save_game_dialog_module.SaveGameDialog(
        lambda: listed.append(True) or [{"name": "slot-a"}],
        lambda _name: None,
        lambda _name: None,
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(ValueError, match="Unknown save dialog mode"):
        dialog.toggle("export")

    dialog.toggle("save")
    dialog._name = "draft"
    dialog.toggle("save")

    assert dialog._mode == ""
    assert dialog._name == "draft"
    assert len(listed) == 1


def test_render_saves_entered_name_and_draws_empty_list(monkeypatch):
    saved = []
    dialog = save_game_dialog_module.SaveGameDialog(
        lambda: [], saved.append, lambda _name: None, lambda *_args, **_kwargs: None
    )
    dialog.toggle("save")
    calls, imgui = _install_render_stubs(
        monkeypatch, input_value="quick-save", button_clicked=True
    )

    dialog.render()

    assert saved == ["quick-save"]
    assert dialog._mode == ""
    assert ("text_disabled", "No saved games.") in imgui.calls
    assert calls["window"][0][1]["test_id"] == "save_game.dialog"
    assert calls["list"] == [("Save_Game_Window/frmInner/frmSave/lstSaves", False)]
    assert any(call[0] == "text" and call[1] == "frmSave/lblSaveName" for call in calls["widgets"])
    assert any(call[0] == "button" and call[-1] for call in calls["widgets"])


def test_render_save_selection_prefills_name_before_input(monkeypatch):
    dialog = save_game_dialog_module.SaveGameDialog(
        lambda: [{"name": "existing-slot"}],
        lambda _name: None,
        lambda _name: None,
        lambda *_args, **_kwargs: None,
    )
    dialog.toggle("save")
    calls, _imgui = _install_render_stubs(monkeypatch, selections=(True,))

    dialog.render()

    assert dialog._name == "existing-slot"
    assert any(call[0] == "button" and call[-1] for call in calls["widgets"])


def test_render_load_selects_row_formats_columns_and_dispatches_load(monkeypatch):
    loaded = []
    rows = [
        {"name": "slot-a"},
        {
            "name": "slot-b",
            "timestamp": "2026-11-08T12:34:56Z",
            "scenario": "Scenario B",
            "country_tag": "UKR",
            "game_time": "1939.01.01",
        },
    ]
    dialog = save_game_dialog_module.SaveGameDialog(
        lambda: rows, lambda _name: None, loaded.append, lambda *_args, **_kwargs: None
    )
    dialog.toggle("load")
    calls, imgui = _install_render_stubs(
        monkeypatch,
        selections=(False, True),
        hovered=(False, False, False, False, True, True, True, True),
        button_clicked=True,
    )

    dialog.render()

    assert loaded == ["slot-b"]
    assert dialog._mode == ""
    assert calls["window"][0][1]["gml_template"] == "Load_Saved_Game"
    assert calls["list"] == [("Load_Saved_Game/frmInner/frmList/lstGames", False)]
    assert any(call[0] == "selectable" and call[1] == "slot-a|132##slot-slot-a" for call in imgui.calls)
    assert any(call[0] == "text_disabled" and call[1] == "\u2014|125" for call in imgui.calls)
    assert any(call == ("text_disabled", "2026-11-08 12:34") for call in imgui.calls)
    assert {call[1] for call in imgui.calls if call[0] == "tooltip"} == {
        "slot-b", "Scenario B", "UKR", "1939.01.01"
    }
    assert any(call[0] == "button" and call[1] == "btnLoadGame" and call[-1] for call in calls["widgets"])


def test_render_closed_list_keeps_load_disabled_and_idle_render_is_noop(monkeypatch):
    loaded = []
    dialog = save_game_dialog_module.SaveGameDialog(
        lambda: [], lambda _name: None, loaded.append, lambda *_args, **_kwargs: None
    )
    dialog.render()
    assert dialog._mode == ""

    dialog.toggle("load")
    calls, _imgui = _install_render_stubs(monkeypatch, list_open=False, button_clicked=True)
    dialog.render()

    assert loaded == []
    assert dialog._mode == "load"
    assert any(call[0] == "button" and call[1] == "btnLoadGame" and not call[-1] for call in calls["widgets"])
