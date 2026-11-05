from __future__ import annotations

from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.shared.panel_widgets import draw_key_value_rows


class TooltipHelpPanel:
    def __init__(self, open_tutorial_cb=None) -> None:
        self._open_tutorial_cb = open_tutorial_cb

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("TOOLTIP HELP", x=840, y=120, w=420, h=360,
                                  test_id="help.panel") as is_open:
            if not is_open:
                return False
            self._render_content()
            return True

    def _render_content(self) -> None:
        imgui.text_wrapped("The controls below expose the current HUD surface without depending on external documentation.")
        imgui.separator()

        draw_key_value_rows(
            (
                ("F1", "Open controls and tooltip help"),
                ("F3", "Save the current session"),
                ("F4", "Open the load-game screen"),
                ("F5", "Open objectives"),
                ("F9", "Open the runtime console"),
                ("F10", "Return to the main menu"),
                ("Left Click", "Select region or unit"),
                ("Right Drag", "Rotate the globe"),
                ("Mouse Wheel", "Zoom the camera"),
            ),
            dim_labels=False,
        )
        imgui.separator()
        imgui.text("Guided tours")
        imgui.begin_disabled(self._open_tutorial_cb is None)
        try:
            if imgui.button(
                "INTERFACE",
                (176.0, 26.0),
                test_id="help.tutorial.interface",
            ):
                self._open_tutorial_cb("interface")
            imgui.same_line()
            if imgui.button(
                "MILITARY",
                (176.0, 26.0),
                test_id="help.tutorial.military",
            ):
                self._open_tutorial_cb("military")
        finally:
            imgui.end_disabled()
