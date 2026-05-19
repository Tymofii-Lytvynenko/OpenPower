from imgui_bundle import imgui

from src.client.ui.components.hud.panel_manager import PanelManager
from src.client.ui.core.primitives import UIPrimitives as Prims


class ToggleBar:
    def __init__(self, panel_manager: PanelManager):
        self.manager = panel_manager

    def render(self):
        viewport = imgui.get_main_viewport()
        pad_x, pad_y = 10.0, 10.0

        imgui.set_next_window_pos(
            imgui.ImVec2(pad_x, viewport.size.y - pad_y),
            imgui.Cond_.always,
            imgui.ImVec2(0.0, 1.0),
        )

        flags = (
            imgui.WindowFlags_.no_decoration
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.always_auto_resize
            | imgui.WindowFlags_.no_background
        )

        if imgui.begin("ToggleBar", True, flags):
            icon_entries = [entry for entry in self.manager.get_entries(toggle_bar_only=True) if entry.icon]

            for index, entry in enumerate(icon_entries):
                if index > 0:
                    imgui.same_line(0, 10)

                if Prims.icon_toggle(entry.icon, entry.color, entry.visible):
                    self.manager.toggle(entry.id)

            imgui.end()
