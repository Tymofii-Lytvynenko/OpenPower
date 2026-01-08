from imgui_bundle import imgui
import polars as pl
from typing import Optional
from datetime import datetime, timedelta
from src.client.services.network_client_service import NetworkClient

class GameLayout:
    """
    Manages the ImGui layout for the active Gameplay session.
    Different from EditorLayout: Focuses on Economy, Date, and Country management.
    """
    
    def __init__(self, net_client: NetworkClient, player_tag: str):
        self.net = net_client
        self.player_tag = player_tag
        
        # UI State
        self.map_mode = "political" # Default for gameplay
        self.show_debug = False
        
        # Date Configuration
        self.start_date = datetime(2001, 1, 1, 0, 0)

    def render(self, selected_region_id: Optional[int], fps: float):
        """Main render pass."""
        self._render_top_bar(fps)
        self._render_region_inspector(selected_region_id)
        
        # TODO: Add Minimap, Ledger, etc.

    def _render_top_bar(self, fps: float):
        """
        The main status bar at the top: Flag, Resources, Date, Speed.
        """
        if imgui.begin_main_menu_bar():
            # 1. Country Info
            imgui.text_colored((0, 1, 1, 1), f"[{self.player_tag}]")
            
            # Fetch Economy Data (Placeholder lookup)
            state = self.net.get_state()
            
            # Try to find our country stats
            balance = 0
            try:
                # Assuming countries_eco.tsv structure
                if "countries" in state.tables:
                    df = state.tables["countries"]
                    row = df.filter(pl.col("id") == self.player_tag)
                    if not row.is_empty():
                        balance = row.select("money_balance").item(0)
            except Exception:
                pass

            imgui.separator()
            imgui.text(f"Treasury: ${balance:,}")
            
            imgui.separator()
            
            # 2. Time & Speed
            tick = state.globals.get("tick", 0)
            date_str = self._format_date(tick)
            imgui.text(f"Date: {date_str}") 
            
            # Spacer
            imgui.dummy((20, 0))
            
            # 3. Map Modes
            if imgui.begin_menu("Map Mode"):
                if imgui.menu_item("Political", "", self.map_mode == "political")[0]:
                    self.map_mode = "political"
                if imgui.menu_item("Terrain", "", self.map_mode == "terrain")[0]:
                    self.map_mode = "terrain"
                imgui.end_menu()

            # 4. FPS / Debug
            main_vp_w = imgui.get_main_viewport().size.x
            imgui.set_cursor_pos_x(main_vp_w - 100)
            imgui.text_disabled(f"FPS: {fps:.0f}")

            imgui.end_main_menu_bar()

    def _render_region_inspector(self, region_id: Optional[int]):
        """
        Bottom-left or Side panel showing region info.
        """
        # Position at bottom left
        vp_h = imgui.get_main_viewport().size.y
        imgui.set_next_window_pos((10, vp_h - 220), imgui.Cond_.first_use_ever)
        imgui.set_next_window_size((250, 200), imgui.Cond_.first_use_ever)
        
        if imgui.begin("Province Info", flags=imgui.WindowFlags_.no_collapse):
            if region_id is not None:
                state = self.net.get_state()
                try:
                    df = state.get_table("regions")
                    row = df.filter(pl.col("id") == region_id).row(0, named=True)
                    
                    imgui.text_colored((1, 1, 0, 1), f"{row.get('name', 'Unknown')}")
                    imgui.separator()
                    
                    owner = row.get("owner", "None")
                    if owner == self.player_tag:
                        imgui.text_colored((0, 1, 0, 1), f"Owner: {owner} (You)")
                    else:
                        imgui.text(f"Owner: {owner}")
                        
                    imgui.text(f"Type: {row.get('type', '-')}")
                    
                    # Population placeholder
                    pop = row.get("pop_15_64", 0) + row.get("pop_14", 0) + row.get("pop_65", 0)
                    imgui.text(f"Population: {pop:,}")
                    
                except Exception:
                    imgui.text("Data unavailable")
            else:
                imgui.text_disabled("Select a province...")
                
        imgui.end()

    def _format_date(self, tick: int) -> str:
        """
        Converts engine ticks to a formatted date string.
        Assuming 1 tick = 1 hour.
        Format: DD.MM.YYYY HH:MM
        """
        current_time = self.start_date + timedelta(hours=tick)
        return current_time.strftime("%d.%m.%Y %H:%M")