from imgui_bundle import imgui
from typing import Optional

from src.client.services.network_client_service import NetworkClient
from src.client.ui.panels.region_inspector import RegionInspectorPanel

class EditorLayout:
    """
    Manages the ImGui layout for the Editor.
    Delegates specific windows to sub-panels and tracks display state.
    """
    def __init__(self, net_client: NetworkClient):
        self.net = net_client
        
        # Sub-panels
        self.inspector = RegionInspectorPanel()
        
        # Map Visualization State
        # Keys are what the user sees, Values are what the MapRenderer understands
        self.layer_options = {
            "Physical (Terrain)": "terrain",
            "Political (Countries)": "political",
            "Debug (Region IDs)": "debug_regions"
        }
        self.layer_keys = list(self.layer_options.keys())
        
        # Default selection
        self.current_layer_label = "Physical (Terrain)" 

    def get_current_render_mode(self) -> str:
        """
        Returns the internal mode string (e.g., 'political') 
        corresponding to the currently selected dropdown item.
        """
        return self.layer_options[self.current_layer_label]

    def render(self, selected_region_id: Optional[int], fps: float):
        """Main UI Render Pass."""
        self._render_menu_bar()
        self._render_info_overlay(fps)
        
        # Pass authoritative GameState to the inspector
        state = self.net.get_state()
        self.inspector.render(selected_region_id, state)

    def _render_menu_bar(self):
        if imgui.begin_main_menu_bar():
            # File Menu
            if imgui.begin_menu("File"):
                # FIX: Added 'False' as the 3rd argument (selected=False)
                # menu_item returns a tuple (clicked, state)
                if imgui.menu_item("Save Map Data", "Ctrl+S", False)[0]:
                    self.net.request_save()
                imgui.end_menu()
                
            # View Menu
            if imgui.begin_menu("View"):
                imgui.text("Map Layer:")
                
                # Combo Box for map modes
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
        Transparent overlay in the top-left corner showing stats.
        """
        # Position 10px from left, 50px from top (below menu bar)
        imgui.set_next_window_pos((10, 50), imgui.Cond_.first_use_ever)
        
        # --- FIX: Added no_inputs and no_focus_on_appearing ---
        # no_inputs: Allows mouse clicks to pass through to the map
        # no_focus_on_appearing: Prevents this window from stealing keyboard focus on load
        flags = (imgui.WindowFlags_.always_auto_resize | 
                 imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_nav |
                 imgui.WindowFlags_.no_inputs | 
                 imgui.WindowFlags_.no_focus_on_appearing)
                 
        # Make background semi-transparent black
        imgui.push_style_color(imgui.Col_.window_bg, (0, 0, 0, 0.5))
        
        if imgui.begin("Overlay", flags=flags):
            imgui.text_colored((0, 1, 0, 1), f"FPS: {fps:.0f}")
            imgui.text(f"Layer: {self.current_layer_label}")
            imgui.separator()
            imgui.text_disabled("Right Click: Pan Map")
            imgui.text_disabled("Scroll: Zoom")
            imgui.text_disabled("Left Click: Select Region")
        imgui.end()
        
        imgui.pop_style_color()