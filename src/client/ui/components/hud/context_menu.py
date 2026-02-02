from typing import Optional, Any
from imgui_bundle import imgui

from src.client.ui.core.composer import UIComposer
from src.client.ui.components.hud.panel_manager import PanelManager

class ContextMenu:
    """
    Manages the Global Right-Click Context Menu for the map.
    Handles the 'queued open' logic to prevent ImGui event conflicts.
    """
    def __init__(self, composer: UIComposer, panel_manager: PanelManager, viewport_ctrl: Any):
        self.composer = composer
        self.panels = panel_manager
        self.viewport = viewport_ctrl
        
        # State
        self._target_id: Optional[int] = None
        self._queued_open: bool = False
        self._popup_id = "global_map_context"

    def show(self, region_id: int):
        """
        Public API to trigger the menu. Safe to call from Input handlers.
        """
        self._target_id = region_id
        self._queued_open = True

    def render(self):
        """
        Must be called within the ImGui frame loop.
        """
        # 1. Handle Queued Open (Safe point inside Frame)
        if self._queued_open:
            imgui.open_popup(self._popup_id)
            self._queued_open = False

        # 2. Render Popup Content
        if self.composer.begin_popup(self._popup_id):
            self._render_content()
            self.composer.end_popup()

    def _render_content(self):
        # 1. Target Header
        if self._target_id is not None:
            imgui.text_disabled(f"Target: Region #{self._target_id}")
            
            if self.composer.draw_menu_item("View Details", "I"):
                self.panels.set_visible("INSPECTOR", True)
                self.viewport.select_region_by_id(self._target_id)
            
            if self.composer.draw_menu_item("Center Camera"):
                self.viewport.focus_on_region(self._target_id)
            
            imgui.separator()

        # 2. Map Modes Menu
        if self.composer.begin_menu("Map Mode"):
            # A. Terrain (Physical) Toggle
            if self.composer.draw_menu_item("Physical (Terrain)"):
                # Switches to terrain mode. 
                # Requires ViewportController.set_map_mode("terrain") to handle disabling overlays.
                if hasattr(self.viewport, "set_map_mode"):
                    self.viewport.set_map_mode("terrain")

            imgui.separator()

            # B. Dynamic Modes (Political, Economic, etc.)
            if hasattr(self.viewport, "map_modes"):
                for key, mode_obj in self.viewport.map_modes.items():
                    # Highlight if active
                    is_active = (getattr(self.viewport, "current_mode_key", "") == key)
                    
                    if imgui.menu_item(mode_obj.name, "", is_active)[0]:
                        self.viewport.set_map_mode(key)
            
            self.composer.end_menu()

        # 3. Tools Menu (Conditional)
        # Check if the Data Inspector panel is registered before showing the menu
        has_data_inspector = any(e.id == "DATA_INSPECTOR" for e in self.panels.get_entries())
        
        if has_data_inspector:
            imgui.separator()
            if self.composer.begin_menu("Tools"):
                is_visible = self.panels.is_visible("DATA_INSPECTOR")
                if imgui.menu_item("Data Inspector", "", is_visible)[0]:
                    self.panels.toggle("DATA_INSPECTOR")
                self.composer.end_menu()

        # 4. System Actions
        imgui.separator()
        if self.composer.draw_menu_item("Close All Panels"):
            for entry in self.panels.get_entries():
                entry.visible = False