from imgui_bundle import imgui
import polars as pl
from typing import Optional, Callable
from src.client.services.network_client_service import NetworkClient

class EditorLayout:
    """
    Manages the ImGui layout for the Editor.
    
    Pattern:
        This is a 'View Component'. It is stateless regarding the game data.
        It strictly renders what is passed to it and delegates commands via the NetworkClient.
    """
    
    def __init__(self, net_client: NetworkClient):
        self.net = net_client
        
        # Events / Callbacks
        # We use a callback pattern to allow the Layout to control the Camera 
        # without hard-coding a dependency on the CameraController.
        self.on_focus_request: Optional[Callable[[float, float], None]] = None 
        
        # UI State (Persistent between frames)
        self.show_region_list = False

    def render(self, selected_region_int_id: Optional[int], fps: float):
        """
        Main entry point to draw all editor UI panels.
        Call this inside the ImGui frame context.
        """
        self._render_menu()
        self._render_inspector(selected_region_int_id)
        
        if self.show_region_list:
            self._render_region_list()
        
        # Debug Overlay (Top Left)
        imgui.set_next_window_pos((10, 50), imgui.Cond_.first_use_ever)
        imgui.begin("Debug", flags=imgui.WindowFlags_.always_auto_resize | imgui.WindowFlags_.no_decoration)
        imgui.text(f"FPS: {fps:.0f}" if fps > 0 else "--")
        imgui.text("Right Click / Middle Mouse: Pan Map")
        imgui.text("Scroll: Zoom")
        imgui.end()

    def _render_menu(self):
        """Draws the main menu bar."""
        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File"):
                if imgui.menu_item("Save Regions", "Ctrl+S")[0]:
                    self.net.request_save()
                imgui.end_menu()
                
            if imgui.begin_menu("View"):
                _, self.show_region_list = imgui.menu_item("Region List", "", self.show_region_list)
                imgui.end_menu()
                
            imgui.end_main_menu_bar()

    def _render_inspector(self, region_int_id: Optional[int]):
        """Draws the properties panel for the selected region."""
        imgui.begin("Region Inspector")
        
        if region_int_id is not None:
            # Fetch data lazily
            state = self.net.get_state()
            regions = state.get_table("regions")
            
            try:
                # Fast Lookup by Int ID using Polars
                # We filter to find the row where 'id' matches.
                row = regions.filter(pl.col("id") == region_int_id).row(0, named=True)
                
                # Display Data
                imgui.text_colored((0, 1, 0, 1), f"{row.get('name', 'Unknown')}")
                
                imgui.text("IDs:")
                imgui.bullet_text(f"Int ID: {region_int_id}")
                imgui.bullet_text(f"Hex ID: {row.get('hex', 'N/A')}")
                
                imgui.separator()
                
                imgui.text(f"Owner: {row.get('owner', 'None')}")
                imgui.text(f"Type:  {row.get('type', '-')}")
                
                imgui.separator()
                imgui.text_disabled("Properties are read-only in this demo.")
                
            except Exception:
                imgui.text_colored((1, 0, 0, 1), "Region Data Error")
                imgui.text(f"Selected ID: {region_int_id}")
                imgui.text_wrapped("The region exists in the map mask but has no entry in the TSV data.")
        else:
            imgui.text_disabled("Select a region on map...")
            
        imgui.end()

    def _render_region_list(self):
        """Draws a searchable/scrollable list of all regions."""
        # The 'True' argument allows the window to be closed (X button)
        is_open = imgui.begin("All Regions", True)[1]
        self.show_region_list = is_open
        
        if is_open:
            state = self.net.get_state()
            regions = state.get_table("regions")
            
            # Limit display count for performance if list is huge
            # In a real app, use imgui.ListClipper for infinite lists.
            limit = 200
            
            imgui.text_disabled(f"Showing first {limit} regions")
            imgui.separator()
            
            for row in regions.head(limit).iter_rows(named=True):
                label = f"{row.get('name', '?')} ({row.get('hex', '?')})"
                
                if imgui.selectable(label)[0]:
                    if self.on_focus_request:
                        # Jump camera to this region
                        cx = row.get('center_x', 0)
                        cy = row.get('center_y', 0)
                        self.on_focus_request(cx, cy)
                        
        imgui.end()