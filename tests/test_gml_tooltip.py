from src.client.ui.core.gml_tooltip import resolve_gml_tooltip_geometry


def test_gml_tooltip_sizes_short_text_and_sits_above_left_of_cursor():
    geometry = resolve_gml_tooltip_geometry(
        "help",
        lambda _text, _wrap_width: (20.0, 12.0),
        (100.0, 80.0),
    )

    assert (geometry.x, geometry.y, geometry.width, geometry.height) == (
        67.0,
        55.0,
        30.0,
        22.0,
    )


def test_gml_tooltip_widens_until_long_content_fits_below_the_frame_width():
    text = "x" * 180

    def measure(value: str, wrap_width: float) -> tuple[float, float]:
        natural_width = len(value) * 10.0
        lines = max(1, (int(natural_width) + int(wrap_width) - 1) // int(wrap_width))
        return min(natural_width, wrap_width), lines * 20.0

    geometry = resolve_gml_tooltip_geometry(text, measure, (700.0, 700.0))

    assert geometry.width == 250.0
    assert geometry.height == 170.0


def test_gml_tooltip_moves_below_and_right_when_above_left_position_is_negative():
    geometry = resolve_gml_tooltip_geometry(
        "long text",
        lambda _text, _wrap_width: (400.0, 12.0),
        (10.0, 5.0),
    )

    assert (geometry.x, geometry.y) == (20.0, 15.0)
