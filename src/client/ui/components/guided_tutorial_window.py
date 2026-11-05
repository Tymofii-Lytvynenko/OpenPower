from __future__ import annotations

from collections.abc import Callable

from imgui_bundle import imgui

from src.client.ui.components.tutorial_arrow_window import TutorialArrowWindow
from src.client.ui.components.tutorial_guide_content import (
    TUTORIAL_GUIDE_MIN_WIDTH,
    TUTORIAL_GUIDE_WIDTH,
    TutorialGuideContent,
)
from src.client.ui.core.containers import WindowManager
from src.client.ui.components.hud.main_bar_geometry import main_bar_bounds
from src.client.ui.core.window_placement import max_unoccupied_horizontal_width
from src.client.ui.core.ui_anchor_registry import UIAnchorRegistry

# Keep auto-placed guides below the 38px shortcut strip and its 8px clearance.
SYSTEM_BAR_CLEARANCE = 46.0


class GuidedTutorialWindow:
    """Shows event-gated guides over the live HUD and its authoritative panels."""

    def __init__(self) -> None:
        self._content = TutorialGuideContent()
        self._arrow = TutorialArrowWindow()
        self._country_info_was_open = False

    @property
    def is_open(self) -> bool:
        return self._content.is_open

    def open(self, guide_id: str) -> None:
        self._content.open(guide_id)
        self._country_info_was_open = False
        self._watch_current_target()

    def close(self) -> None:
        self._content.close()
        UIAnchorRegistry.set_targets(())

    def on_interaction(self, interaction: str) -> None:
        self._content.on_interaction(interaction)

    def render(self, panel_visible_cb: Callable[[str], bool]) -> None:
        if not self.is_open:
            UIAnchorRegistry.set_targets(())
            return
        self._content.advance_if_ready(panel_visible_cb)
        if not self.is_open:
            UIAnchorRegistry.set_targets(())
            return
        self._watch_current_target()

        viewport = imgui.get_main_viewport()
        self._record_viewport_target(viewport)
        main_bar = main_bar_bounds(
            float(viewport.size.x), float(viewport.size.y),
            float(viewport.pos.x), float(viewport.pos.y),
        )
        country_info_open = bool(panel_visible_cb("COUNTRY_MORE_INFO"))
        if country_info_open and not self._country_info_was_open:
            # Country Information may already be above this persistent window in ImGui's draw order.
            imgui.set_next_window_focus()
        self._country_info_was_open = country_info_open
        bottom_clearance = max(
            0.0,
            float(viewport.pos.y + viewport.size.y - main_bar.y) + 8.0,
        )
        available_width = max_unoccupied_horizontal_width(
            float(viewport.size.x),
            WindowManager.visible_frame_placements(),
        )
        if not country_info_open and available_width < TUTORIAL_GUIDE_MIN_WIDTH:
            return
        width = min(
            TUTORIAL_GUIDE_WIDTH,
            max(TUTORIAL_GUIDE_MIN_WIDTH, available_width),
        )
        size = self._content.window_size(panel_visible_cb, width)
        if country_info_open:
            # Keep the guide visible on compact screens so its close-panel step
            # remains actionable; center it while leaving the target's close slot clear.
            x = max(0.0, (float(viewport.size.x) - size[0]) / 2.0)
            y = SYSTEM_BAR_CLEARANCE
        else:
            x = 24.0
            y = 78.0
        with WindowManager.window(
            self._content.title,
            x=x,
            y=y,
            w=size[0],
            h=size[1],
            flags=imgui.WindowFlags_.no_title_bar,
            test_id="game.tutorial.window",
            gml_template="Tutorial_Window",
            size_override=size,
            avoid_overlaps=not country_info_open,
            follow_position=country_info_open,
            top_clearance=SYSTEM_BAR_CLEARANCE,
            bottom_clearance=bottom_clearance,
        ) as is_open:
            if not is_open:
                self.close()
                return
            self._content.render(
                self.close,
                panel_visible_cb=panel_visible_cb,
                test_id_prefix="game",
                window_width=size[0],
            )
        self._watch_current_target()
        # Some targets can disappear, such as the date while speed controls
        # are open; use the step's visible fallback rather than lose the arrow.
        target = next(
            (anchor for target_id in self._content.arrow_targets
             if (anchor := UIAnchorRegistry.get(target_id)) is not None),
            None,
        )
        if target is not None:
            self._arrow.render(target)

    def _watch_current_target(self) -> None:
        UIAnchorRegistry.set_targets(self._content.arrow_targets)

    def _record_viewport_target(self, viewport) -> None:
        test_id = "world.viewport"
        if test_id not in self._content.arrow_targets:
            return
        center_x = float(viewport.pos.x) + float(viewport.size.x) / 2.0
        center_y = float(viewport.pos.y) + float(viewport.size.y) / 2.0
        UIAnchorRegistry.record(test_id, center_x - 0.5, center_y - 0.5, 1.0, 1.0)
