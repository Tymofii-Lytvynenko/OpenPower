from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

from src.client.ui.testing import map_information_surface as surface_module


class RecordingImgui:
    def __init__(
        self,
        *,
        clicked: set[str] | None = None,
        mouse_position: tuple[float, float] = (150, 320),
        tab_down: bool = False,
    ) -> None:
        self.clicked = clicked or set()
        self.mouse_position = mouse_position
        self.tab_down = tab_down
        self.buttons: list[str] = []
        self.cursor_positions: list[tuple[float, float]] = []
        self.WindowFlags_ = SimpleNamespace(
            no_decoration=1,
            no_bring_to_front_on_focus=2,
            no_background=4,
        )
        self.Key = SimpleNamespace(tab=9)

    def set_cursor_screen_pos(self, position: tuple[float, float]) -> None:
        self.cursor_positions.append(position)

    def button(self, label: str, *_args, **_kwargs) -> bool:
        self.buttons.append(label)
        return label in self.clicked

    def same_line(self) -> None:
        pass

    def get_mouse_pos(self):
        return SimpleNamespace(x=self.mouse_position[0], y=self.mouse_position[1])

    def get_io(self):
        return SimpleNamespace(display_size=SimpleNamespace(y=900))

    def is_key_down(self, key: int) -> bool:
        return self.tab_down and key == self.Key.tab


class FakeWindowManager:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    @classmethod
    @contextmanager
    def window(cls, *args, **kwargs):
        cls.calls.append((args, kwargs))
        yield True


class FakeSelection:
    instances: list["FakeSelection"] = []

    def __init__(self, renderer, _map_renderer, client) -> None:
        self.renderer = renderer
        self.client = client
        self.selected_unit_ids: set[str] = set()
        self.presses: list[tuple[float, float, int]] = []
        self.releases: list[tuple[float, float, int]] = []
        self.instances.append(self)

    def on_mouse_press(self, x: float, y: float, button: int) -> None:
        self.presses.append((x, y, button))
        unit = self.renderer.get_unit_at(x, y)
        if unit is not None:
            self.selected_unit_ids.add(unit.unit_id)

    def on_mouse_release(self, x: float, y: float, button: int) -> None:
        self.releases.append((x, y, button))

    def clear_selection(self) -> None:
        self.selected_unit_ids.clear()


class FakeMapInformationWindows:
    instances: list["FakeMapInformationWindows"] = []

    def __init__(self, viewer) -> None:
        self.viewer = viewer
        self.render_selected_unit = Mock()
        self.render_region = Mock()
        self.instances.append(self)


def install_surface_ui(monkeypatch, imgui: RecordingImgui) -> None:
    FakeWindowManager.calls.clear()
    FakeSelection.instances.clear()
    FakeMapInformationWindows.instances.clear()
    monkeypatch.setattr(surface_module, "WindowManager", FakeWindowManager)
    monkeypatch.setattr(surface_module, "UnitInteractionController", FakeSelection)
    monkeypatch.setattr(surface_module, "MapInformationWindows", FakeMapInformationWindows)
    monkeypatch.setattr(surface_module, "imgui", imgui)


def test_map_information_surface_dispatches_unit_and_region_interactions(monkeypatch) -> None:
    imgui = RecordingImgui(
        clicked={"unit-1", "Deselect", "Select two"},
        mouse_position=(150, 320),
        tab_down=True,
    )
    install_surface_ui(monkeypatch, imgui)
    state = object()
    client = object()
    viewer = "USA"

    render = surface_module.build_map_information_surface(state, client, viewer)
    render()

    selection = FakeSelection.instances[0]
    windows = FakeMapInformationWindows.instances[0]
    assert windows.viewer == viewer
    assert selection.client is client
    assert selection.presses == [(160, 220, surface_module.arcade.MOUSE_BUTTON_LEFT)]
    assert selection.releases == [(160, 220, surface_module.arcade.MOUSE_BUTTON_LEFT)]
    assert selection.selected_unit_ids == {"unit-1", "unit-2"}
    selected_args = windows.render_selected_unit.call_args.args
    assert selected_args[:2] == (state, {"unit-1", "unit-2"})
    assert selected_args[2]("unit-2").screen_x == 240
    assert selected_args[3] == 900
    assert windows.render_region.call_args.args == (state, 1, (150, 320))
    assert windows.render_region.call_args.kwargs == {"active": True}
    assert "Deselect" in imgui.buttons
    assert "Select two" in imgui.buttons
    assert FakeWindowManager.calls[0][1]["test_id"] == "map.info.fixture"


def test_map_information_surface_handles_no_selection_and_outside_region_hit(monkeypatch) -> None:
    imgui = RecordingImgui(mouse_position=(320, 320), tab_down=False)
    install_surface_ui(monkeypatch, imgui)
    state = object()

    surface_module.build_map_information_surface(state, object(), "USA")()

    selection = FakeSelection.instances[0]
    windows = FakeMapInformationWindows.instances[0]
    assert selection.presses == []
    assert selection.releases == []
    assert selection.selected_unit_ids == set()
    assert windows.render_region.call_args.args == (state, None, (320, 320))
    assert windows.render_region.call_args.kwargs == {"active": False}
