"""Small map overlay that explains and cancels a pending unit order."""
from __future__ import annotations

from collections.abc import Callable

from src.client.ui.core.instrumented_imgui import imgui


class UnitOrderTargetingPrompt:
    """Keep the active map-targeting mode visible while a unit order is pending."""

    def render(self, mode: str | None, on_cancel: Callable[[], None]) -> None:
        if mode is None:
            return

        display_size = imgui.get_io().display_size
        imgui.set_next_window_pos(
            (display_size.x * 0.5, 48.0),
            imgui.Cond_.always,
            (0.5, 0.0),
        )
        flags = (
            imgui.WindowFlags_.no_decoration
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_saved_settings
            | imgui.WindowFlags_.always_auto_resize
        )
        opened, _ = imgui.begin(
            "Unit order targeting",
            None,
            flags,
            test_id="unit.order.targeting",
        )
        try:
            if not opened:
                return
            if mode == "move":
                imgui.text("MOVE — click a destination. Esc or right-click cancels.", test_id="unit.order.targeting.label")
            else:
                imgui.text(
                    "ATTACK MOVE — click a destination. Hostile contact triggers combat; neutral entry needs confirmation.",
                    test_id="unit.order.targeting.label",
                )
            imgui.same_line()
            if imgui.button("Cancel", test_id="unit.order.cancel"):
                on_cancel()
        finally:
            imgui.end()
