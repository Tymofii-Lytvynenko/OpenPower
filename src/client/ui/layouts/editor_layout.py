from imgui_bundle import imgui
from typing import Optional

from src.client.services.network_client_service import NetworkClient
from src.client.ui.layouts.base_layout import BaseLayout
from src.client.ui.theme import GAMETHEME

class EditorLayout(BaseLayout):
    """
    Manages the ImGui layout for the Map Editor.
    
    Features:
    - Top Menu Bar (File, View).
    - Info Overlay (FPS, Keybinds).
    - Layer Switching (Terrain vs Political).
    """
    def __init__(self, net_client: NetworkClient, viewport_ctrl):
        super().__init__(net_client, viewport_ctrl)
        
        # Map Visualization State
        # Maps the UI Label -> The internal mode string used by MapRenderer
        self.layer_options = {
            "Physical (Terrain)": "terrain",
            "Political (Countries)": "political",
            # "Debug (Region IDs)": "debug_regions" # Future feature
        }
        self.layer_keys = list(self.layer_options.keys())
        self.current_layer_label = "Political (Countries)" 

    def get_current_render_mode(self) -> str:
        """Called by EditorView to know what to draw."""
        return self.layer_options[self.current_layer_label]

    def render(self, fps: float):
        """Main UI Render Pass."""
        # 1. Setup Theme
        self.composer.setup_frame()
        
        # Plain white FPS in corner
        self._render_fps_counter(fps)
        
        # Right-click menu still works for map layers
        self._render_context_menu()
        
        # Floating debug info (already handles its own position)
        self._render_info_overlay(fps)
        
    def _render_menu_bar(self):
        if imgui.begin_main_menu_bar():
            # -- File Menu --
            if imgui.begin_menu("File"):
                # "Ctrl+S" is just visual text here; actual input handled in View
                if imgui.menu_item("Save Map Data", "Ctrl+S", False)[0]:
                    self.net.request_save()
                imgui.end_menu()
                
            # -- View Menu --
            if imgui.begin_menu("View"):
                imgui.text("Map Layer:")
                
                # Custom Combo Box for Layer Selection
                if imgui.begin_combo("##layer_combo", self.current_layer_label):
                    for label in self.layer_keys:
                        is_selected = (label == self.current_layer_label)
                        if imgui.selectable(label, is_selected)[0]:
                            self.current_layer_label = label
                        
                        if is_selected:
                            imgui.set_item_default_focus()
                    imgui.end_combo()
                imgui.end_menu()
                
            imgui.end_main_menu_bar()

    def _render_info_overlay(self, fps: float):
        """
        Draws a transparent floating window with debug info.
        """
        imgui.set_next_window_pos((10, 50), imgui.Cond_.first_use_ever)
        
        flags = (imgui.WindowFlags_.always_auto_resize | 
                 imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_nav |
                 imgui.WindowFlags_.no_inputs | 
                 imgui.WindowFlags_.no_focus_on_appearing)
                 
        # Use theme for semi-transparent overlay background
        imgui.push_style_color(imgui.Col_.window_bg, GAMETHEME.col_overlay_bg)
        
        if imgui.begin("Overlay", flags=flags):
            imgui.text_colored(GAMETHEME.col_positive, f"FPS: {fps:.0f}")
            imgui.text(f"Layer: {self.current_layer_label}")
            imgui.separator()
            imgui.text_disabled("Right Click: Pan Map")
            imgui.text_disabled("Scroll: Zoom")
            imgui.text_disabled("Left Click: Select Region")
        imgui.end()
        
        imgui.pop_style_color()