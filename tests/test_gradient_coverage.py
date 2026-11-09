import pytest

from src.client.utils import gradient
from src.client.utils.gradient import get_heatmap_color, lerp_color


def test_lerp_color_returns_start_when_range_is_degenerate() -> None:
    start = (12, 34, 56)
    end = (200, 210, 220)

    assert lerp_color(0.75, 4.0, 4.0, start, end) == start


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-1.0, (0, 10, 20)),
        (0.5, (50, 110, 135)),
        (2.0, (100, 210, 250)),
    ],
    ids=["clamps-low", "interpolates", "clamps-high"],
)
def test_lerp_color_clamps_and_interpolates_channels(
    value: float,
    expected: tuple[int, int, int],
) -> None:
    assert lerp_color(value, 0.0, 1.0, (0, 10, 20), (100, 210, 250)) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-1.0, (0, 0, 255)),
        (0.0, (0, 0, 255)),
        (0.125, (0, 127, 255)),
        (0.25, (0, 255, 255)),
        (0.375, (0, 255, 127)),
        (0.5, (0, 255, 0)),
        (0.625, (127, 255, 0)),
        (0.75, (255, 255, 0)),
        (0.875, (255, 127, 0)),
        (1.0, (255, 0, 0)),
        (2.0, (255, 0, 0)),
    ],
    ids=[
        "clamps-below",
        "blue-stop",
        "blue-to-cyan",
        "cyan-stop",
        "cyan-to-green",
        "green-stop",
        "green-to-yellow",
        "yellow-stop",
        "yellow-to-red",
        "red-stop",
        "clamps-above",
    ],
)
def test_heatmap_color_covers_stops_and_intervals(
    value: float,
    expected: tuple[int, int, int],
) -> None:
    assert get_heatmap_color(value) == expected


def test_heatmap_color_uses_final_stop_when_no_interval_matches(monkeypatch) -> None:
    monkeypatch.setattr(gradient, "range", lambda _stop_count: (), raising=False)

    assert get_heatmap_color(0.5) == (255, 0, 0)
