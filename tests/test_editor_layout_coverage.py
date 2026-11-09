from types import SimpleNamespace
from unittest.mock import Mock

from src.client.ui.layouts import editor_layout as editor_layout_module


class EditorImGuiStub:
    def __init__(
        self,
        *,
        main_menu: bool = True,
        menus: dict[str, bool] | None = None,
        combos: dict[str, bool] | None = None,
        selected: set[str] | None = None,
        save: bool = True,
        overlay: bool = True,
    ) -> None:
        self.main_menu = main_menu
        self.menus = menus or {}
        self.combos = combos or {}
        self.selected = selected or set()
        self.save = save
        self.overlay = overlay
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.WindowFlags_ = SimpleNamespace(
            no_decoration=1,
            always_auto_resize=2,
            no_background=4,
        )

    def begin_main_menu_bar(self) -> bool:
        return self.main_menu

    def begin_menu(self, label: str) -> bool:
        return self.menus.get(label, True)

    def menu_item(self, *args: object) -> tuple[bool, bool]:
        self.calls.append(("menu_item", args))
        return self.save, False

    def end_menu(self) -> None:
        self.calls.append(("end_menu", ()))

    def begin_combo(self, label: str, current: str) -> bool:
        self.calls.append(("begin_combo", (label, current)))
        return self.combos.get(label, True)

    def selectable(self, label: str, is_selected: bool) -> tuple[bool, bool]:
        self.calls.append(("selectable", (label, is_selected)))
        return label in self.selected, False

    def end_combo(self) -> None:
        self.calls.append(("end_combo", ()))

    def end_main_menu_bar(self) -> None:
        self.calls.append(("end_main_menu_bar", ()))

    def set_next_window_pos(self, position: tuple[int, int]) -> None:
        self.calls.append(("set_next_window_pos", (position,)))

    def begin(self, name: str, visible: bool, flags: int) -> bool:
        self.calls.append(("begin", (name, visible, flags)))
        return self.overlay

    def text_colored(self, color: str, text: str) -> None:
        self.calls.append(("text_colored", (color, text)))

    def end(self) -> None:
        self.calls.append(("end", ()))


def install_editor_ui(monkeypatch, imgui_stub: EditorImGuiStub) -> Mock:
    theme = SimpleNamespace(apply=Mock(), colors=SimpleNamespace(positive="green"))
    monkeypatch.setattr(editor_layout_module, "imgui", imgui_stub)
    monkeypatch.setattr(editor_layout_module, "GAMETHEME", theme)
    return theme.apply


def test_render_saves_and_updates_layer_and_projection(monkeypatch) -> None:
    imgui = EditorImGuiStub(selected={"Terrain", "Planar"})
    apply_theme = install_editor_ui(monkeypatch, imgui)
    network = SimpleNamespace(request_save=Mock())
    projection_changes: list[str] = []
    layout = editor_layout_module.EditorLayout(
        network,
        viewport_ctrl=object(),
        on_projection_change=projection_changes.append,
    )

    layout.render(59.6)

    apply_theme.assert_called_once_with()
    network.request_save.assert_called_once_with(is_editor=True)
    assert layout.get_current_render_mode() == "terrain"
    layout.current_layer_label = "Unknown"
    assert layout.get_current_render_mode() == "political"
    assert layout.current_projection_label == "Planar"
    assert projection_changes == ["planar"]
    assert ("text_colored", ("green", "FPS: 60")) in imgui.calls
    assert any(name == "end_combo" for name, _args in imgui.calls)


def test_render_handles_closed_file_layer_and_overlay_and_missing_callback(monkeypatch) -> None:
    imgui = EditorImGuiStub(
        menus={"File": False, "View": True},
        combos={"Layer": False, "Projection": True},
        selected={"Planar"},
        save=False,
        overlay=False,
    )
    apply_theme = install_editor_ui(monkeypatch, imgui)
    layout = editor_layout_module.EditorLayout(
        SimpleNamespace(request_save=Mock()),
        viewport_ctrl=object(),
    )

    layout.render(30)

    apply_theme.assert_called_once_with()
    assert layout.current_layer_label == "Political"
    assert layout.current_projection_label == "Planar"
    assert not any(name == "text_colored" for name, _args in imgui.calls)
    assert not any(name == "menu_item" for name, _args in imgui.calls)
    assert imgui.calls[-1] == ("end", ())


def test_render_skips_closed_main_menu_and_draws_overlay(monkeypatch) -> None:
    imgui = EditorImGuiStub(main_menu=False)
    apply_theme = install_editor_ui(monkeypatch, imgui)
    layout = editor_layout_module.EditorLayout(object(), object())

    layout.render(24.4)

    apply_theme.assert_called_once_with()
    assert ("text_colored", ("green", "FPS: 24")) in imgui.calls
    assert not any(name == "begin_menu" for name, _args in imgui.calls)
    assert imgui.calls[-1] == ("end", ())
