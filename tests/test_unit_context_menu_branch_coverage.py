from importlib import import_module
from types import SimpleNamespace
from unittest.mock import Mock

from src.client.ui.components.hud.unit_context_menu import UnitContextMenu


class _FakeImgui:
    HoveredFlags_ = SimpleNamespace(allow_when_disabled=1)

    def __init__(self, *, popup_open=False, clicked=(), hovered=()):
        self.popup_open = popup_open
        self.clicked = set(clicked)
        self.hovered = iter(hovered)
        self.calls = []

    def open_popup(self, popup_id):
        self.calls.append(("open_popup", popup_id))

    def begin_popup(self, popup_id, *, test_id):
        self.calls.append(("begin_popup", popup_id, test_id))
        return self.popup_open

    def end_popup(self):
        self.calls.append(("end_popup",))

    def text_disabled(self, text):
        self.calls.append(("text_disabled", text))

    def separator(self):
        self.calls.append(("separator",))

    def begin_disabled(self):
        self.calls.append(("begin_disabled",))

    def end_disabled(self):
        self.calls.append(("end_disabled",))

    def menu_item(self, label, *_args, test_id):
        self.calls.append(("menu_item", label, test_id))
        return (test_id in self.clicked,)

    def is_item_hovered(self, _flags):
        return next(self.hovered, False)

    def set_tooltip(self, text):
        self.calls.append(("set_tooltip", text))


class _FakeComposer:
    def __init__(self, *, menu_open=False, clicked=()):
        self.menu_open = menu_open
        self.clicked = set(clicked)
        self.calls = []

    def begin_menu(self, label):
        self.calls.append(("begin_menu", label))
        return self.menu_open

    def draw_menu_item(self, label):
        self.calls.append(("draw_menu_item", label))
        return label in self.clicked

    def end_menu(self):
        self.calls.append(("end_menu",))


def _menu(monkeypatch, *, imgui, composer=None, **callbacks):
    module = import_module("src.client.ui.components.hud.unit_context_menu")
    monkeypatch.setattr(module, "imgui", imgui)
    return UnitContextMenu(
        composer or _FakeComposer(),
        callbacks.get("on_deselect", Mock()),
        callbacks.get("on_view_units_list", Mock()),
        callbacks.get("on_set_readiness"),
        callbacks.get("on_split"),
        callbacks.get("on_merge"),
        callbacks.get("on_move_requested"),
        callbacks.get("on_attack_requested"),
    )


def test_render_opens_popup_and_dispatches_available_actions(monkeypatch):
    imgui = _FakeImgui(
        popup_open=True,
        clicked={
            "unit.context.move",
            "unit.context.move_and_attack",
            "unit.context.deselect",
            "unit.context.merge_with",
            "unit.context.split",
            "unit.context.view_list",
        },
    )
    composer = _FakeComposer(
        menu_open=True,
        clicked={"Park", "Ready", "Fortify", "Deselect"},
    )
    callbacks = {
        "on_deselect": Mock(),
        "on_view_units_list": Mock(),
        "on_set_readiness": Mock(),
        "on_split": Mock(),
        "on_merge": Mock(),
        "on_move_requested": Mock(),
        "on_attack_requested": Mock(),
    }
    menu = _menu(monkeypatch, imgui=imgui, composer=composer, **callbacks)

    menu.show("unit-7")
    menu.render()
    imgui.popup_open = False
    menu.render()

    assert imgui.calls.count(("open_popup", "unit_context_menu")) == 1
    assert imgui.calls.count(("end_popup",)) == 1
    assert callbacks["on_deselect"].call_count == 1
    assert callbacks["on_view_units_list"].call_args.args == ("unit-7",)
    assert callbacks["on_set_readiness"].call_args_list == [
        (("unit-7", "parked"),),
        (("unit-7", "ready"),),
        (("unit-7", "fortified"),),
    ]
    assert callbacks["on_move_requested"].call_args.args == ("unit-7",)
    assert callbacks["on_attack_requested"].call_args.args == ("unit-7",)
    assert callbacks["on_merge"].call_args.args == ("unit-7",)
    assert callbacks["on_split"].call_args.args == ("unit-7",)


def test_content_without_unit_returns_before_drawing(monkeypatch):
    imgui = _FakeImgui()
    composer = _FakeComposer()
    menu = _menu(monkeypatch, imgui=imgui, composer=composer)

    menu._render_content()

    assert imgui.calls == []
    assert composer.calls == []


def test_unavailable_and_disabled_actions_show_hover_help(monkeypatch):
    imgui = _FakeImgui(hovered=(True, False, False, False))
    menu = _menu(
        monkeypatch,
        imgui=imgui,
        on_move_requested=Mock(),
    )
    menu.show("unit-8", orders_enabled=False)

    menu._render_content()

    assert ("set_tooltip", "Select one of your own units before issuing this order.") in imgui.calls
    assert ("menu_item", "Move", "unit.context.move") in imgui.calls
    assert ("menu_item", "Move and attack", "unit.context.move_and_attack") in imgui.calls
    assert imgui.calls.count(("begin_disabled",)) == 4
    assert imgui.calls.count(("end_disabled",)) == 4


def test_menu_items_can_be_declined_and_readiness_callback_can_be_missing(monkeypatch):
    imgui = _FakeImgui(popup_open=True)
    composer = _FakeComposer(menu_open=True, clicked={"Park", "Deselect"})
    on_deselect = Mock()
    menu = _menu(
        monkeypatch,
        imgui=imgui,
        composer=composer,
        on_deselect=on_deselect,
        on_move_requested=Mock(),
        on_attack_requested=Mock(),
    )
    menu.show("unit-9")

    menu._render_content()

    assert on_deselect.call_count == 1
    assert ("menu_item", "Move", "unit.context.move") in imgui.calls
    assert ("menu_item", "Move and attack", "unit.context.move_and_attack") in imgui.calls
    assert ("end_menu",) in composer.calls
    assert ("draw_menu_item", "Ready") in composer.calls
    assert ("draw_menu_item", "Fortify") in composer.calls
