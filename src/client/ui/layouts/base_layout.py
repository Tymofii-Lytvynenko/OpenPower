import arcade
from typing import Optional, Any, Dict
from src.client.ui.panels.data_insp_panel import DataInspectorPanel
from src.client.services.network_client_service import NetworkClient
from src.client.ui.panels.region_inspector import RegionInspectorPanel
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME
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
                if self.composer.draw_menu_item("Political"):
                    if hasattr(self, 'map_mode'): setattr(self, 'map_mode', "political")
                if self.composer.draw_menu_item("Terrain"):
                    if hasattr(self, 'map_mode'): setattr(self, 'map_mode', "terrain")
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