"""Reference geometry shared by the main bar and its anchored windows."""
from __future__ import annotations

from src.client.ui.layouts.gml_layout import GMLRect, get_gml_layout


def main_bar_bounds(width: float, height: float, x=0.0, y=0.0) -> GMLRect:
    layout = get_gml_layout("Main_Bar")
    bar_width = min(float(layout.width), width)
    bar_height = min(float(layout.height), height)
    return GMLRect(
        x + (width - bar_width) / 2.0,
        y + max(0.0, height - bar_height - 8.0),
        bar_width,
        bar_height,
    )
