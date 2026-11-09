from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import src.client.ui.components.guided_tutorial_window as tutorial_window_module
from src.client.ui.components.guided_tutorial_window import GuidedTutorialWindow


class FakeTutorialContent:
    def __init__(self) -> None:
        self.is_open = False
        self.title = "GUIDE"
        self.arrow_targets = ("world.viewport",)
        self.size_override = None
        self.close_on_advance = False
        self.opened_ids = []
        self.interactions = []
        self.advance_callbacks = []
        self.size_calls = []
        self.render_calls = []
        self.close_count = 0

    def open(self, guide_id: str) -> None:
        self.opened_ids.append(guide_id)
        self.is_open = True

    def close(self) -> None:
        self.close_count += 1
        self.is_open = False

    def on_interaction(self, interaction: str) -> None:
        self.interactions.append(interaction)

    def advance_if_ready(self, panel_visible_cb) -> None:
        self.advance_callbacks.append(panel_visible_cb)
        if self.close_on_advance:
            self.is_open = False

    def window_size(self, panel_visible_cb, width: float) -> tuple[float, float]:
        self.size_calls.append((panel_visible_cb, width))
        return self.size_override or (width, 180.0)

    def render(self, on_close, **kwargs) -> None:
        self.render_calls.append((on_close, kwargs))


@pytest.fixture
def tutorial_harness(monkeypatch):
    content = FakeTutorialContent()
    arrow = Mock()
    viewport = SimpleNamespace(
        pos=SimpleNamespace(x=10.0, y=20.0),
        size=SimpleNamespace(x=800.0, y=600.0),
    )
    imgui = SimpleNamespace(
        WindowFlags_=SimpleNamespace(no_title_bar=object()),
        get_main_viewport=Mock(return_value=viewport),
        set_next_window_focus=Mock(),
    )
    recorded_targets = []
    recorded_rectangles = []
    anchors = {}
    registry = SimpleNamespace(
        set_targets=lambda targets: recorded_targets.append(tuple(targets)),
        record=lambda *rectangle: recorded_rectangles.append(rectangle),
        get=lambda target_id: anchors.get(target_id),
    )
    available_width = {"value": 500.0}
    main_bar_y = {"value": 500.0}
    window_open = {"value": True}
    window_calls = []
    placements = [object()]
    manager = SimpleNamespace(
        visible_frame_placements=Mock(return_value=placements),
    )

    @contextmanager
    def window(title, **kwargs):
        window_calls.append((title, kwargs))
        yield window_open["value"]

    manager.window = window
    main_bar_bounds = Mock(
        side_effect=lambda *_args: SimpleNamespace(y=main_bar_y["value"]),
    )
    unoccupied_width = Mock(
        side_effect=lambda _width, _placements: available_width["value"],
    )

    monkeypatch.setattr(tutorial_window_module, "TutorialGuideContent", lambda: content)
    monkeypatch.setattr(tutorial_window_module, "TutorialArrowWindow", lambda: arrow)
    monkeypatch.setattr(tutorial_window_module, "imgui", imgui)
    monkeypatch.setattr(tutorial_window_module, "UIAnchorRegistry", registry)
    monkeypatch.setattr(tutorial_window_module, "WindowManager", manager)
    monkeypatch.setattr(tutorial_window_module, "main_bar_bounds", main_bar_bounds)
    monkeypatch.setattr(
        tutorial_window_module,
        "max_unoccupied_horizontal_width",
        unoccupied_width,
    )

    return SimpleNamespace(
        content=content,
        arrow=arrow,
        viewport=viewport,
        imgui=imgui,
        anchors=anchors,
        recorded_targets=recorded_targets,
        recorded_rectangles=recorded_rectangles,
        available_width=available_width,
        main_bar_y=main_bar_y,
        window_open=window_open,
        window_calls=window_calls,
        placements=placements,
        manager=manager,
        main_bar_bounds=main_bar_bounds,
        unoccupied_width=unoccupied_width,
    )


def test_open_interaction_close_and_closed_render_manage_targets(tutorial_harness) -> None:
    harness = tutorial_harness
    harness.content.arrow_targets = ("mini_map.map",)
    window = GuidedTutorialWindow()

    window.open("interface")
    window.on_interaction("mini_map.navigate")

    assert window.is_open is True
    assert harness.content.opened_ids == ["interface"]
    assert harness.content.interactions == ["mini_map.navigate"]
    assert harness.recorded_targets == [("mini_map.map",)]

    window.close()
    assert window.is_open is False
    assert harness.content.close_count == 1
    assert harness.recorded_targets[-1] == ()

    window.render(lambda _panel_id: False)

    assert harness.recorded_targets[-1] == ()
    harness.imgui.get_main_viewport.assert_not_called()
    assert harness.window_calls == []


def test_render_stops_when_advance_closes_the_guide(tutorial_harness) -> None:
    harness = tutorial_harness
    harness.content.close_on_advance = True
    window = GuidedTutorialWindow()
    window.open("military")

    window.render(lambda _panel_id: False)

    assert harness.content.advance_callbacks
    assert harness.recorded_targets[-1] == ()
    harness.imgui.get_main_viewport.assert_not_called()
    assert harness.window_calls == []


def test_render_skips_narrow_auto_placement_after_recording_viewport_target(
    tutorial_harness,
) -> None:
    harness = tutorial_harness
    harness.content.arrow_targets = ("world.viewport",)
    harness.available_width["value"] = 259.0
    window = GuidedTutorialWindow()
    window.open("interface")

    window.render(lambda _panel_id: False)

    assert harness.recorded_rectangles == [
        ("world.viewport", 409.5, 319.5, 1.0, 1.0),
    ]
    harness.main_bar_bounds.assert_called_once_with(800.0, 600.0, 10.0, 20.0)
    harness.unoccupied_width.assert_called_once_with(800.0, harness.placements)
    assert harness.content.size_calls == []
    assert harness.window_calls == []


@pytest.mark.parametrize(
    ("available_width", "expected_width"),
    [(350.0, 350.0), (500.0, 400.0)],
    ids=["available-width", "capped-width"],
)
def test_auto_placed_render_uses_available_width_and_first_visible_arrow(
    tutorial_harness,
    available_width: float,
    expected_width: float,
) -> None:
    harness = tutorial_harness
    harness.content.arrow_targets = ("missing", "visible", "world.viewport")
    harness.available_width["value"] = available_width
    anchor = object()
    harness.anchors["visible"] = anchor
    window = GuidedTutorialWindow()
    window.open("interface")

    window.render(lambda _panel_id: False)

    assert harness.recorded_rectangles == [
        ("world.viewport", 409.5, 319.5, 1.0, 1.0),
    ]
    assert harness.content.size_calls == [(harness.content.advance_callbacks[0], expected_width)]
    assert len(harness.window_calls) == 1
    title, options = harness.window_calls[0]
    assert title == "GUIDE"
    assert options == {
        "x": 24.0,
        "y": 78.0,
        "w": expected_width,
        "h": 180.0,
        "flags": harness.imgui.WindowFlags_.no_title_bar,
        "test_id": "game.tutorial.window",
        "gml_template": "Tutorial_Window",
        "size_override": (expected_width, 180.0),
        "avoid_overlaps": True,
        "follow_position": False,
        "top_clearance": 46.0,
        "bottom_clearance": 128.0,
    }
    on_close, render_options = harness.content.render_calls[0]
    assert callable(on_close)
    assert render_options == {
        "panel_visible_cb": harness.content.advance_callbacks[0],
        "test_id_prefix": "game",
        "window_width": expected_width,
    }
    assert harness.recorded_targets[-2:] == [
        ("missing", "visible", "world.viewport"),
        ("missing", "visible", "world.viewport"),
    ]
    assert harness.arrow.render.call_args.args == (anchor,)
    assert harness.imgui.set_next_window_focus.call_count == 0


@pytest.mark.parametrize(
    ("viewport_width", "expected_x"),
    [(300.0, 0.0), (800.0, 150.0)],
    ids=["clamped-to-left", "centered"],
)
def test_country_info_keeps_guide_visible_and_focuses_only_on_transition(
    tutorial_harness,
    viewport_width: float,
    expected_x: float,
) -> None:
    harness = tutorial_harness
    harness.viewport.size.x = viewport_width
    harness.content.arrow_targets = ("missing",)
    harness.content.size_override = (500.0, 220.0)
    harness.available_width["value"] = 150.0
    harness.main_bar_y["value"] = 700.0
    window = GuidedTutorialWindow()
    window.open("interface")
    panel_visible = lambda panel_id: panel_id == "COUNTRY_MORE_INFO"

    window.render(panel_visible)
    window.render(panel_visible)

    harness.imgui.set_next_window_focus.assert_called_once_with()
    assert len(harness.window_calls) == 2
    for _, options in harness.window_calls:
        assert options["x"] == expected_x
        assert options["y"] == 46.0
        assert options["w"] == 500.0
        assert options["h"] == 220.0
        assert options["avoid_overlaps"] is False
        assert options["follow_position"] is True
        assert options["bottom_clearance"] == 0.0
    assert all(width == 260.0 for _, width in harness.content.size_calls)
    assert harness.recorded_rectangles == []
    assert harness.arrow.render.call_count == 0

    window.close()
    window.open("interface")
    window.render(panel_visible)
    assert harness.imgui.set_next_window_focus.call_count == 2


def test_closed_imgui_window_closes_guide_without_rendering_content(tutorial_harness) -> None:
    harness = tutorial_harness
    harness.window_open["value"] = False
    window = GuidedTutorialWindow()
    window.open("interface")

    window.render(lambda _panel_id: False)

    assert window.is_open is False
    assert harness.content.close_count == 1
    assert harness.content.render_calls == []
    assert harness.recorded_targets[-1] == ()
    assert harness.arrow.render.call_count == 0
