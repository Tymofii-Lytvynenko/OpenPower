from __future__ import annotations

from dataclasses import dataclass

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.ui_anchor_registry import UIAnchor


TUTORIAL_ARROW_SIZE = 50.0


@dataclass(frozen=True, slots=True)
class TutorialArrowGeometry:
    window_x: float
    window_y: float
    target_x: float
    target_y: float


def resolve_tutorial_arrow_geometry(
    target: UIAnchor,
    viewport_position: tuple[float, float],
    viewport_size: tuple[float, float],
) -> TutorialArrowGeometry | None:
    viewport_x, viewport_y = viewport_position
    viewport_width, viewport_height = viewport_size
    if viewport_width < TUTORIAL_ARROW_SIZE or viewport_height <= 0.0:
        return None

    target_x = target.x + target.width / 2.0
    target_y = target.y
    window_x = min(
        max(target_x - TUTORIAL_ARROW_SIZE / 2.0, viewport_x),
        viewport_x + viewport_width - TUTORIAL_ARROW_SIZE,
    )
    window_y = max(viewport_y, target_y - TUTORIAL_ARROW_SIZE)
    if target_y - window_y < 8.0:
        return None
    return TutorialArrowGeometry(window_x, window_y, target_x, target_y)


class TutorialArrowWindow:
    """Draws the source-sized pointer above the current tutorial target."""

    def render(self, target: UIAnchor) -> None:
        viewport = imgui.get_main_viewport()
        geometry = resolve_tutorial_arrow_geometry(
            target,
            (float(viewport.pos.x), float(viewport.pos.y)),
            (float(viewport.size.x), float(viewport.size.y)),
        )
        if geometry is None:
            return

        flags = (
            imgui.WindowFlags_.no_decoration
            | imgui.WindowFlags_.no_inputs
            | imgui.WindowFlags_.no_focus_on_appearing
            | imgui.WindowFlags_.no_bring_to_front_on_focus
            | imgui.WindowFlags_.no_background
            | imgui.WindowFlags_.no_saved_settings
        )
        with WindowManager.window(
            "##TutorialArrow",
            x=geometry.window_x,
            y=geometry.window_y,
            w=TUTORIAL_ARROW_SIZE,
            h=TUTORIAL_ARROW_SIZE,
            closable=False,
            flags=flags,
            test_id="game.tutorial.arrow",
            gml_template="Tutorial_Arrow_Window",
            size_override=(TUTORIAL_ARROW_SIZE, TUTORIAL_ARROW_SIZE),
            padding=(0.0, 0.0),
            follow_position=True,
        ) as is_open:
            if not is_open:
                return

        self._draw(
            imgui.get_foreground_draw_list(),
            geometry.window_x,
            geometry.window_y,
            geometry.target_x,
            geometry.target_y,
        )

    @staticmethod
    def _draw(draw, window_x: float, window_y: float, target_x: float, target_y: float) -> None:
        tip_x = target_x
        tip_y = target_y - 2.0
        tip_y_local = tip_y - window_y
        head_height = min(18.0, max(7.0, (tip_y_local - 3.0) * 0.5))
        head_top = window_y + max(2.0, tip_y_local - head_height)
        head_width = min(24.0, max(10.0, head_height * 1.25))
        outline = imgui.get_color_u32((0.02, 0.03, 0.04, 0.98))
        fill = imgui.get_color_u32((1.0, 0.78, 0.20, 1.0))

        draw.add_rect_filled(
            (tip_x - 5.0, window_y + 2.0),
            (tip_x + 5.0, head_top + 4.0),
            outline,
        )
        draw.add_triangle_filled(
            (tip_x, tip_y),
            (tip_x - head_width / 2.0 - 2.0, head_top),
            (tip_x + head_width / 2.0 + 2.0, head_top),
            outline,
        )
        draw.add_rect_filled(
            (tip_x - 2.5, window_y + 3.0),
            (tip_x + 2.5, head_top + 2.0),
            fill,
        )
        draw.add_triangle_filled(
            (tip_x, tip_y - 2.0),
            (tip_x - head_width / 2.0, head_top + 2.0),
            (tip_x + head_width / 2.0, head_top + 2.0),
            fill,
        )
