from typing import Optional
import polars as pl
from imgui_bundle import imgui, icons_fontawesome_6

from src.client.services.network_client_service import NetworkClient
from src.client.ui.core.theme import GAMETHEME

# Components
from src.client.ui.components.hud.central_bar import CentralBar
from src.client.ui.components.hud.system_bar import SystemBar
from src.client.ui.components.hud.toggle_bar import ToggleBar
from src.client.ui.components.hud.panel_manager import PanelManager

# Panels
from src.client.ui.panels.economy_panel import EconomyPanel
from src.client.ui.panels.politics_panel import PoliticsPanel
from src.client.ui.panels.military_panel import MilitaryPanel
from src.client.ui.panels.demographics_panel import DemographicsPanel
from src.client.ui.panels.region_inspector import RegionInspectorPanel
from src.client.ui.panels.data_insp_panel import DataInspectorPanel

class GameLayout:
    """
    Composition root for the Game HUD.
    """
    def __init__(self, net_client: NetworkClient, player_tag: str, viewport_ctrl):
        self.net = net_client
        self.local_player_tag = player_tag
        self.viewport_ctrl = viewport_ctrl

        # 1. Compose Managers
        self.panel_manager = PanelManager()
        
        # 2. Register Panels
        self.panel_manager.register("POL", PoliticsPanel(), icons_fontawesome_6.ICON_FA_BUILDING_COLUMNS, GAMETHEME.colors.politics)
        self.panel_manager.register("MIL", MilitaryPanel(), icons_fontawesome_6.ICON_FA_PERSON_MILITARY_RIFLE, GAMETHEME.colors.military)
        self.panel_manager.register("ECO", EconomyPanel(), icons_fontawesome_6.ICON_FA_SACK_DOLLAR, GAMETHEME.colors.economy)
        self.panel_manager.register("DEM", DemographicsPanel(), icons_fontawesome_6.ICON_FA_PEOPLE_GROUP, GAMETHEME.colors.demographics)
        
        # Tools (No Icon = Not in Toggle Bar)
        self.panel_manager.register("INSPECTOR", RegionInspectorPanel())
        self.panel_manager.register("DATA_INSPECTOR", DataInspectorPanel())

        # 3. Compose HUD Bars
        self.central_bar = CentralBar()
        self.system_bar = SystemBar()
        self.toggle_bar = ToggleBar(self.panel_manager)

        # State Cache
        self._last_selected_id: Optional[int] = None
        self._cached_target_tag: str = player_tag

    def render(self, selected_region_id: Optional[int], fps: float, nav_service):
        GAMETHEME.apply()
        state = self.net.get_state()

        # Logic: Determine context
        target_tag, is_own = self._resolve_active_context(state, selected_region_id)

        # Render Bars
        self.system_bar.render(self.net, nav_service)
        
        # Central bar returns context switch requests (e.g. from debug dropdown)
        req_tag = self.central_bar.render(state, self.net, target_tag, is_own)
        if req_tag:
            self._cached_target_tag = req_tag

        self.toggle_bar.render()

        # Render Panels
        self.panel_manager.render_all(
            state, 
            target_tag=target_tag, 
            is_own_country=is_own,
            selected_region_id=selected_region_id,
            on_focus_request=self._on_focus_region
        )

        self._render_fps(fps)

    def _on_focus_region(self, region_id):
        self.viewport_ctrl.focus_on_region(region_id)

    def _render_fps(self, fps: float):
        imgui.set_next_window_pos((10, 10))
        flags = (imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_inputs | 
                 imgui.WindowFlags_.no_background |
                 imgui.WindowFlags_.always_auto_resize)
        
        if imgui.begin("##FPS", True, flags):
            imgui.text_colored((1,1,1,1), f"{fps:.0f}")
        imgui.end()

    def _resolve_active_context(self, state, region_id: Optional[int]) -> tuple[str, bool]:
        """
        Determines who we are looking at based on selection.
        """
        if region_id != self._last_selected_id:
            self._last_selected_id = region_id
            
            # Reset to local player if deselect
            if not region_id:
                self._cached_target_tag = self.local_player_tag
            else:
                if "regions" in state.tables:
                    try:
                        # FIX: Use .item(0, col) for typesafe scalar extraction
                        # This avoids Pylance errors with expression calls
                        owner = state.tables["regions"] \
                            .filter(pl.col("id") == region_id) \
                            .item(0, "owner")
                            
                        self._cached_target_tag = owner if owner and owner != "None" else self.local_player_tag
                    except Exception:
                        self._cached_target_tag = self.local_player_tag

        return self._cached_target_tag, (self._cached_target_tag == self.local_player_tag)
    
    def show_context_menu(self, region_id):
        self.panel_manager.set_visible("INSPECTOR", True)