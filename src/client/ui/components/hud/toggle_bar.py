from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.components.hud.panel_manager import PanelManager
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.components.hud.main_bar_geometry import main_bar_bounds
from src.client.ui.layouts.gml_layout import get_gml_layout


class ToggleBar:
    def __init__(self, panel_manager: PanelManager):
        self.manager = panel_manager

    def render(self):
        viewport = imgui.get_main_viewport()
        pad_x, pad_y = 10.0, 10.0
        icon_entries = [entry for entry in self.manager.get_entries(toggle_bar_only=True)
                        if entry.icon]
        if not icon_entries:
            return
        icon_size = 50.0
        item_gap = 10.0
        style = imgui.get_style()
        estimated_width = (
            style.window_padding.x * 2.0
            + len(icon_entries) * icon_size
            + max(0, len(icon_entries) - 1) * item_gap
        )
        main_bar = main_bar_bounds(viewport.size.x, viewport.size.y)
        left_gutter = max(0.0, (viewport.size.x - main_bar.width) / 2.0)
        compact = left_gutter < estimated_width + pad_x

        if compact:
            # Keep the panel launchers above compact-view panels, which can cover
            # the lower-left strip while they are open.
            system_bar_height = get_gml_layout("System_Bar_Window").height
            top = viewport.pos.y + system_bar_height + 2.0
            imgui.push_style_var(imgui.StyleVar_.window_padding, (0.0, 0.0))
            imgui.set_next_window_pos(
                imgui.ImVec2(viewport.pos.x + pad_x + style.window_padding.x, top),
                imgui.Cond_.always,
                imgui.ImVec2(0.0, 0.0),
            )
        else:
            imgui.set_next_window_pos(
                imgui.ImVec2(viewport.pos.x + pad_x, viewport.pos.y + viewport.size.y - pad_y),
                imgui.Cond_.always,
                imgui.ImVec2(0.0, 1.0),
            )

        flags = (
            imgui.WindowFlags_.no_decoration
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.always_auto_resize
            | imgui.WindowFlags_.no_background
        )

        expanded = imgui.begin("ToggleBar", True, flags, test_id="hud.panel_toggles")
        try:
            if expanded:
                for index, entry in enumerate(icon_entries):
                    if index > 0:
                        imgui.same_line(0, 10)

                    if Prims.icon_toggle(entry.icon, entry.color, entry.visible,
                                         test_id=f"hud.panel.{entry.id.lower()}", accessible_label=getattr(entry, "title", entry.id)):
                        self.manager.toggle(entry.id)
        finally:
            imgui.end()
            if compact:
                imgui.pop_style_var()
