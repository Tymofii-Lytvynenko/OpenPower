from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

from src.client.ui.testing import unit_movement_surface as surface_module


class FakeGameLayout:
    instances: list["FakeGameLayout"] = []

    def __init__(self, client, country_tag, viewport, settings, window) -> None:
        self.constructor_args = (client, country_tag, viewport, settings, window)
        self.unit_move_orders = SimpleNamespace(request=Mock())
        self.render = Mock()
        self.instances.append(self)


class FakeSelection:
    instances: list["FakeSelection"] = []

    def __init__(self, map_renderer, unit_renderer, client, *, on_move_requested) -> None:
        self.constructor_args = (map_renderer, unit_renderer, client)
        self.on_move_requested = on_move_requested
        self.move_units_to_target = Mock()
        self.instances.append(self)


def install_movement_surface(monkeypatch, *, clicked: set[str]):
    FakeGameLayout.instances.clear()
    FakeSelection.instances.clear()
    button_calls = []

    def button(label: str, **kwargs) -> bool:
        button_calls.append((label, kwargs))
        return label in clicked

    window_manager = SimpleNamespace(window=Mock(return_value=nullcontext(None)))
    monkeypatch.setattr(surface_module, "GameLayout", FakeGameLayout)
    monkeypatch.setattr(surface_module, "UnitInteractionController", FakeSelection)
    monkeypatch.setattr(surface_module, "WindowManager", window_manager)
    monkeypatch.setattr(surface_module, "imgui", SimpleNamespace(button=button))
    return button_calls, window_manager


def test_movement_surface_sends_clicks_to_the_production_move_port(monkeypatch) -> None:
    labels = {
        "unit-1 -> POL",
        "unit-2 -> POL",
        "unit-2 -> DEU",
        "unit-1 -> UKR",
    }
    button_calls, window_manager = install_movement_surface(monkeypatch, clicked=labels)
    state, client, context = object(), object(), SimpleNamespace(target_tag="UKR", selected_region_id=3)
    settings, window, navigation, viewport = object(), object(), object(), object()

    draw = surface_module.build_unit_movement_surface(
        state, client, context, settings, window, navigation, viewport
    )
    draw()

    layout = FakeGameLayout.instances[0]
    selection = FakeSelection.instances[0]
    assert layout.constructor_args == (client, "UKR", viewport, settings, window)
    assert selection.constructor_args == (None, None, client)
    assert selection.on_move_requested is layout.unit_move_orders.request
    assert [call.args for call in selection.move_units_to_target.call_args_list] == [
        ({"unit-1"}, 2, 52.0, 21.0),
        ({"unit-2"}, 2, 52.1, 21.1),
        ({"unit-2"}, 3, 51.0, 13.0),
        ({"unit-1"}, 1, 50.0, 30.0),
    ]
    assert [label for label, _kwargs in button_calls] == [
        "unit-1 -> POL",
        "unit-2 -> POL",
        "unit-2 -> DEU",
        "unit-1 -> UKR",
    ]
    assert button_calls[0][1] == {"test_id": "map.move.unit-1.POL"}
    window_manager.window.assert_called_once_with(
        "Map movement request input",
        x=30,
        y=100,
        w=220,
        h=180,
        closable=False,
        test_id="map.move.fixture",
    )
    layout.render.assert_called_once_with(3, 60.0, navigation, state)


def test_movement_surface_renders_without_issuing_unrequested_moves(monkeypatch) -> None:
    button_calls, _window_manager = install_movement_surface(monkeypatch, clicked=set())
    context = SimpleNamespace(target_tag="USA", selected_region_id=None)
    state, client, settings, window, navigation, viewport = (object() for _ in range(6))

    draw = surface_module.build_unit_movement_surface(
        state, client, context, settings, window, navigation, viewport
    )
    draw()

    assert len(button_calls) == 4
    FakeSelection.instances[0].move_units_to_target.assert_not_called()
    FakeGameLayout.instances[0].render.assert_called_once_with(None, 60.0, navigation, state)
