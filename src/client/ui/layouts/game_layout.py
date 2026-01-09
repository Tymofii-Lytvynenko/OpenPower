from imgui_bundle import imgui
import polars as pl
from typing import Optional
from datetime import datetime, timedelta

from src.client.services.network_client_service import NetworkClient
from src.client.ui.panels.region_inspector import RegionInspectorPanel

class GameLayout:
    """
    Manages the ImGui layout for the active Gameplay session.
    """
    def __init__(self, net_client: NetworkClient, player_tag: str):
        self.net = net_client
        self.player_tag = player_tag
        
        # Reuse the generic inspector
        self.inspector = RegionInspectorPanel()
        
        # UI State
        self.map_mode = "political" 
        self.start_date = datetime(2001, 1, 1, 0, 0)

    def render(self, selected_region_id: Optional[int], fps: float):
        """Main render pass."""
        self._render_top_bar(fps)
        
        # Render the inspector reusing the shared component
        state = self.net.get_state()
        self.inspector.render(selected_region_id, state)

    def _render_top_bar(self, fps: float):
        """The main status bar: Flag, Resources, Date, Speed."""
        if imgui.begin_main_menu_bar():
            # 1. Country Info
            imgui.text_colored((0, 1, 1, 1), f"[{self.player_tag}]")
            
            # Fetch Economy Data
            state = self.net.get_state()
            balance = 0
            try:
                if "countries" in state.tables:
                    df = state.tables["countries"]
                    # Efficiently get single value
                    res = df.filter(pl.col("id") == self.player_tag).select("money_balance")
                    if not res.is_empty():
                        balance = res.item(0, 0)
            except Exception:
                pass

            imgui.separator()
            imgui.text(f"Treasury: ${balance:,}")
            imgui.separator()
            
            # 2. Time & Speed
            tick = state.globals.get("tick", 0)
            date_str = self._format_date(tick)
            imgui.text(f"Date: {date_str}") 
            
            imgui.dummy((20, 0))
            
            # 3. Map Modes
            if imgui.begin_menu("Map Mode"):
                if imgui.menu_item("Political", "", self.map_mode == "political")[0]:
                    self.map_mode = "political"
                if imgui.menu_item("Terrain", "", self.map_mode == "terrain")[0]:
                    self.map_mode = "terrain"
                imgui.end_menu()

            # 4. FPS
            main_vp_w = imgui.get_main_viewport().size.x
            imgui.set_cursor_pos_x(main_vp_w - 80)
            imgui.text_disabled(f"{fps:.0f} FPS")

            imgui.end_main_menu_bar()

    def _format_date(self, tick: int) -> str:
        current_time = self.start_date + timedelta(hours=tick)
        return current_time.strftime("%d.%m.%Y %H:%M")