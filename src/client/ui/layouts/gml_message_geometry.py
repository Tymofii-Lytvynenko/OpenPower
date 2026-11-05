"""Measure and apply the source auto-height behavior used by GML message dialogs."""
from __future__ import annotations

from dataclasses import dataclass
import math

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.layouts.gml_layout import GMLLayoutSession, get_gml_layout, gml_style


@dataclass(frozen=True, slots=True)
class GMLMessageGeometry:
    template: str
    window_width: float
    window_height: float
    message_height: float
    button_y: float
    message_path: str
    button_paths: tuple[str, ...]


def measure_gml_message_geometry(
    template: str,
    message: str,
    viewport_height: float,
) -> GMLMessageGeometry:
    layout = get_gml_layout(template)
    message_path = f"{template}/lblMessage"
    message_component = layout.component(message_path)
    if message_component is None:
        raise KeyError(f"GML message dialog {template!r} is missing its message control.")

    with gml_style():
        text_height = float(
            imgui.calc_text_size(str(message), wrap_width=message_component.rect.width).y
        )
    if not math.isfinite(text_height):
        text_height = message_component.rect.height

    return geometry_for_gml_message_height(template, text_height, viewport_height)


def geometry_for_gml_message_height(
    template: str,
    text_height: float,
    viewport_height: float,
) -> GMLMessageGeometry:
    layout = get_gml_layout(template)
    message_path = f"{template}/lblMessage"
    message_component = layout.component(message_path)
    button_components = tuple(
        component
        for button_id in ("btnOk", "btnCancel")
        if (component := layout.component(f"{template}/{button_id}")) is not None
    )
    if message_component is None or not button_components:
        raise KeyError(f"GML message dialog {template!r} is missing its message or answer controls.")
    if not math.isfinite(float(text_height)):
        text_height = message_component.rect.height

    unchanged = abs(text_height - message_component.rect.height) < 0.5
    if unchanged:
        message_height = message_component.rect.height
        button_y = button_components[0].rect.y
        window_height = float(layout.height)
    else:
        # REFERENCE resizes the message label, then places its answer buttons 12 px below it.
        message_height = max(1.0, math.ceil(text_height) + 4.0)
        button_y = message_component.rect.y + message_height + 12.0
        window_height = button_y + button_components[0].rect.height + 10.0

    max_height = max(64.0, float(viewport_height) - 24.0)
    if window_height > max_height:
        window_height = max_height
        message_height = max(
            1.0,
            window_height
            - message_component.rect.y
            - 12.0
            - button_components[0].rect.height
            - 10.0,
        )
        button_y = message_component.rect.y + message_height + 12.0

    return GMLMessageGeometry(
        template=template,
        window_width=float(layout.width),
        window_height=window_height,
        message_height=message_height,
        button_y=button_y,
        message_path=message_path,
        button_paths=tuple(component.path for component in button_components),
    )


def apply_gml_message_geometry(
    session: GMLLayoutSession | None,
    geometry: GMLMessageGeometry,
) -> None:
    if session is None or session.layout.template != geometry.template:
        return

    session.resize_component(geometry.message_path, height=geometry.message_height)
    for path in geometry.button_paths:
        button_rect = session.rect_for(path)
        session.move_component(path, y=geometry.button_y - button_rect.y)
