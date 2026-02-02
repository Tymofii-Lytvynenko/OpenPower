import arcade
from typing import Optional, Any, Dict
from src.client.ui.panels.data_insp_panel import DataInspectorPanel
from src.client.services.network_client_service import NetworkClient
from src.client.ui.panels.region_inspector import RegionInspectorPanel
from src.client.ui.composer import UIComposer
from src.client.ui.core.theme import GAMETHEME
from imgui_bundle import imgui

class BaseLayout:
    """
    BaseLayout acts as the UI composition root.
    """

    def __init__(self, net_client: NetworkClient, viewport_ctrl: Any):
        self.net = net_client
        self.viewport_ctrl = viewport_ctrl
        self.composer = UIComposer(GAMETHEME)
        self.panels: Dict[str, Dict[str, Any]] = {}

        # State for the Right-Click Context Menu.
        self._menu_target_id: Optional[int] = None
        
        # --- FIX: Додаємо прапорець для відкладеного відкриття ---
        self._queued_popup_open: bool = False
        
        self.register_panel("INSPECTOR", RegionInspectorPanel(), visible=False)
        self.register_panel("DATA_INSPECTOR", DataInspectorPanel(), visible=False)

    def register_panel(self, panel_id: str, instance: Any, visible: bool = True, **metadata):
        self.panels[panel_id] = {
            "instance": instance,
            "visible": visible,
            **metadata
        }
    
    def show_context_menu(self, region_id: int):
        """
        Public API to trigger the context menu.
        Changed to QUEUE the action instead of executing immediately.
        This prevents crashing when called from an Input Event outside the render loop.
        """
        self._menu_target_id = region_id
        # Замість прямого виклику open_popup, ми просимо зробити це на наступному кадрі
        self._queued_popup_open = True 

    def _render_fps_counter(self, fps: float):
        """
        Draws a plain FPS counter in the top-left corner.
        No panel, no background, just raw text.
        """
        # Position at top-left with a small 10px padding
        imgui.set_next_window_pos((10, 10))
        
        # Flags to make the window completely invisible/non-interactive
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_inputs | 
                 imgui.WindowFlags_.no_move | 
                 imgui.WindowFlags_.no_background |
                 imgui.WindowFlags_.always_auto_resize)
                 
        if imgui.begin("##FPS_Overlay", True, flags):
            # Render as pure white text
            imgui.text_colored((1.0, 1.0, 1.0, 1.0), f"{fps:.0f}")
        imgui.end()

    def _render_panels(self, state: Any, **extra_ctx):
        for panel_id, data in self.panels.items():
            if not data["visible"]:
                continue
            panel_instance = data["instance"]
            still_open = panel_instance.render(self.composer, state, **extra_ctx)
            if still_open is False:
                data["visible"] = False

    def _render_context_menu(self):
        """
        Draws the popup content. 
        Also handles the queued 'open' command safely inside the render loop.
        """
        # --- FIX: Обробляємо чергу тут, всередині ImGui Frame ---
        if self._queued_popup_open:
            self.composer.open_popup("global_map_context")
            self._queued_popup_open = False
        # -------------------------------------------------------

        if self.composer.begin_popup("global_map_context"):
            target_id = self._menu_target_id

            if target_id is not None:
                imgui.text_disabled(f"Target: Region #{target_id}")
                
                if self.composer.draw_menu_item("View Details", "I"):
                    self.panels["INSPECTOR"]["visible"] = True
                    self.viewport_ctrl.select_region_by_id(target_id)
                
                if self.composer.draw_menu_item("Center Camera"):
                    self.viewport_ctrl.focus_on_region(target_id)
                
                imgui.separator()

            if self.composer.begin_menu("Map Mode"):
                # Terrain Toggle (Overlay Mode)
                if self.composer.draw_menu_item("Physical (Terrain)"):
                    # This is handled by renderer.draw(mode=...) logic in GameView
                    # You might need to expose a callback or state variable here.
                    if hasattr(self, 'map_mode'): setattr(self, 'map_mode', "terrain")

                imgui.separator()
                
                # Dynamic Map Modes (Visual Overlay)
                # We assume viewport_ctrl exposes available modes
                if hasattr(self.viewport_ctrl, "map_modes"):
                    for key, mode_obj in self.viewport_ctrl.map_modes.items():
                        is_active = (self.viewport_ctrl.current_mode_key == key)
                        if imgui.menu_item(mode_obj.name, "", is_active)[0]:
                            self.viewport_ctrl.set_map_mode(key)
                            # Ensure we are in political/overlay mode, not pure terrain
                            if hasattr(self, 'map_mode'): setattr(self, 'map_mode', "political")
                
                self.composer.end_menu()

            if "DATA_INSPECTOR" in self.panels:
                imgui.separator()
                if self.composer.begin_menu("Tools"):
                    is_visible = self.panels["DATA_INSPECTOR"]["visible"]
                    if imgui.menu_item("Data Inspector", "", is_visible)[0]:
                        self.panels["DATA_INSPECTOR"]["visible"] = not is_visible
                    self.composer.end_menu()

            imgui.separator()
            if self.composer.draw_menu_item("Close All Panels"):
                for p in self.panels.values(): p["visible"] = False

            self.composer.end_popup()

    def is_panel_visible(self, panel_id: str) -> bool:
        return self.panels.get(panel_id, {}).get("visible", False)

    def toggle_panel(self, panel_id: str):
        if panel_id in self.panels:
            self.panels[panel_id]["visible"] = not self.panels[panel_id]["visible"]

    def _on_focus_region(self, region_id: int, image_x: float, image_y: float):
        self.viewport_ctrl.focus_on_region(region_id)