from imgui_bundle import imgui
import polars as pl
from src.client.network_client import NetworkClient

class EditorLayout:
    def __init__(self, net_client: NetworkClient):
        self.net = net_client
        self.on_focus_request = None 
        self.show_region_list = False

    def render(self, selected_region_int_id: int | None, fps: float):
        self._render_menu()
        self._render_inspector(selected_region_int_id)
        if self.show_region_list:
            self._render_region_list()
        
        # Debug Overlay
        imgui.set_next_window_pos((10, 50), imgui.Cond_.first_use_ever)
        imgui.begin("Debug", flags=imgui.WindowFlags_.always_auto_resize | imgui.WindowFlags_.no_decoration)
        imgui.text(f"FPS: {1.0/fps:.1f}" if fps > 0 else "--")
        imgui.end()

    def _render_menu(self):
        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File"):
                if imgui.menu_item("Save Regions", "Ctrl+S")[0]:
                    self.net.request_save()
                imgui.end_menu()
            if imgui.begin_menu("View"):
                _, self.show_region_list = imgui.menu_item("Region List", "", self.show_region_list)
                imgui.end_menu()
            imgui.end_main_menu_bar()

    def _render_inspector(self, region_int_id: int | None):
        imgui.begin("Region Inspector")
        if region_int_id is not None:
            state = self.net.get_state()
            regions = state.get_table("regions")
            
            try:
                # Fast Lookup by Int ID
                row = regions.filter(pl.col("id") == region_int_id).row(0, named=True)
                
                imgui.text_colored((0, 1, 0, 1), f"{row.get('name', 'Unknown')}")
                
                # Show HEX to user (Human Readable ID)
                imgui.text(f"Hex ID: {row.get('hex', 'N/A')}")
                
                imgui.separator()
                imgui.text(f"Owner: {row.get('owner', 'None')}")
                imgui.text(f"Type: {row.get('type', '-')}")
                
            except Exception:
                imgui.text_colored((1, 0, 0, 1), "Region not defined in TSV")
                imgui.text(f"Raw Int: {region_int_id}")
        else:
            imgui.text_disabled("Select a region on map...")
        imgui.end()

    def _render_region_list(self):
        if imgui.begin("All Regions", True)[1]:
            state = self.net.get_state()
            regions = state.get_table("regions").head(200) # Limit for UI perf
            
            for row in regions.iter_rows(named=True):
                # Display Name + Hex
                label = f"{row.get('name', '?')} ({row.get('hex', '?')})"
                if imgui.selectable(label)[0]:
                    if self.on_focus_request:
                        # Assuming center_x/y exist
                        self.on_focus_request(row.get('center_x', 0), row.get('center_y', 0))
        imgui.end()