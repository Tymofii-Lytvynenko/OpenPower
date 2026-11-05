from src.client.ui.components.tutorial_arrow_window import resolve_tutorial_arrow_geometry
from src.client.ui.core.ui_anchor_registry import UIAnchor


def test_tutorial_arrow_points_to_the_target_top_center() -> None:
    geometry = resolve_tutorial_arrow_geometry(
        UIAnchor(100.0, 120.0, 80.0, 24.0),
        (0.0, 0.0),
        (1280.0, 720.0),
    )

    assert geometry is not None
    assert geometry.window_x == 115.0
    assert geometry.window_y == 70.0
    assert geometry.target_x - geometry.window_x == 25.0
    assert geometry.target_y - geometry.window_y == 50.0


def test_tutorial_arrow_stays_inside_the_viewport_near_its_edges() -> None:
    geometry = resolve_tutorial_arrow_geometry(
        UIAnchor(0.0, 18.0, 20.0, 20.0),
        (5.0, 10.0),
        (100.0, 80.0),
    )

    assert geometry is not None
    assert geometry.window_x == 5.0
    assert geometry.window_y == 10.0
    assert geometry.target_x - geometry.window_x == 5.0
    assert geometry.target_y - geometry.window_y == 8.0
