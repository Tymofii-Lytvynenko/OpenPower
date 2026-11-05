"""Initial placement for the main in-game information windows."""
from __future__ import annotations

from src.client.ui.core.instrumented_imgui import imgui


# All five source-sized panels fit edge to edge at 1473 logical pixels with
# the Economy panel's 19-pixel right margin.
WIDE_LAYOUT_MIN_WIDTH = 1473.0

_COMPACT_POSITIONS = {
    "politics": (10.0, 100.0),
    # Leave the compact system strip and bottom central bar unobstructed.
    "treaties": (535.0, 42.0),
    "military": (260.0, 100.0),
    "demographics": (520.0, 100.0),
    "economy": (0.0, 100.0),
}

_WIDE_POSITIONS = {
    "politics": (0.0, 0.0),
    "treaties": (260.0, 18.0),
    "military": (700.0, 164.0),
    "demographics": (970.0, 100.0),
    "economy": (0.0, 130.0),
}


def main_pillar_position(panel_id: str) -> tuple[float, float]:
    """Return a first-open position that keeps the GML-sized panels readable together."""
    viewport_width = float(imgui.get_io().display_size.x)
    if viewport_width <= 0.0:
        viewport_width = float(imgui.get_main_viewport().size.x)

    positions = (
        _WIDE_POSITIONS
        if viewport_width >= WIDE_LAYOUT_MIN_WIDTH
        else _COMPACT_POSITIONS
    )
    return positions[panel_id]
