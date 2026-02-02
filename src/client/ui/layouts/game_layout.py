from typing import Optional
import polars as pl

# Third-party imports
import arcade 
from imgui_bundle import imgui, icons_fontawesome_6

# Internal - UI & Theme
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME
from src.client.services.network_client_service import NetworkClient

# Internal - Components
from src.client.ui.components.hud.central_bar import CentralBar
from src.client.ui.components.hud.system_bar import SystemBar
from src.client.ui.components.hud.toggle_bar import ToggleBar

# Internal - Panels
from src.client.ui.layouts.base_layout import BaseLayout
from src.client.ui.panels.politics_panel import PoliticsPanel
from src.client.ui.panels.military_panel import MilitaryPanel
from src.client.ui.panels.economy_panel import EconomyPanel
from src.client.ui.panels.demographics_panel import DemographicsPanel
from src.client.ui.panels.data_insp_panel import DataInspectorPanel

class GameLayout(BaseLayout):
    """
    The primary HUD Layout for the Gameplay View.
    Orchestrates context switching between the Player's country and Selected foreign countries.
    """

    def __init__(self, net_client: NetworkClient, player_tag: str, viewport_ctrl):
        super().__init__(net_client, viewport_ctrl)
        
        self.local_player_tag = player_tag
        self.map_mode = "political"

        # Cache for selection lookup optimization
        self._last_selected_id: Optional[int] = None
        self._cached_target_tag: str = player_tag

        # --- Panel Registry ---
        self.register_panel("POL", PoliticsPanel(), icon=f"{icons_fontawesome_6.ICON_FA_BUILDING_COLUMNS}", color=GAMETHEME.colors.politics, visible=False)
        self.register_panel("MIL", MilitaryPanel(), icon=f"{icons_fontawesome_6.ICON_FA_PERSON_MILITARY_RIFLE}", color=GAMETHEME.colors.military, visible=False)
        self.register_panel("ECO", EconomyPanel(), icon=f"{icons_fontawesome_6.ICON_FA_SACK_DOLLAR}", color=GAMETHEME.colors.economy, visible=False)
        self.register_panel("DEM", DemographicsPanel(), icon=f"{icons_fontawesome_6.ICON_FA_PEOPLE_GROUP}", color=GAMETHEME.colors.demographics, visible=False)
        
        self.register_panel("DATA_INSPECTOR", DataInspectorPanel(), visible=False)

        # --- HUD Components ---
        self.central_bar = CentralBar()
        self.system_bar = SystemBar()
        self.toggle_bar = ToggleBar()

    def render(self, selected_region_id: Optional[int], fps: float, nav_service):
        """
        The Main UI Render Loop.
        """
        # 1. Setup Frame
        self.composer.setup_frame()
        state = self.net.get_state()

        # 2. Determine "Who are we looking at?"
        target_tag, is_own_country = self._resolve_active_context(state, selected_region_id)

        # 3. Global Overlays
        self._render_fps_counter(fps)
        self._render_context_menu()

        # 4. HUD Bars
        self.system_bar.render(self.composer, self.net, nav_service)
        self.toggle_bar.render(self.composer, self.panels)
        
        # Central Bar shows the TARGET country, not necessarily the player's
        self.central_bar.render(
            self.composer, 
            state, 
            self.net, 
            target_tag,
            is_own_country
        )

        # 5. Interactive Panels
        # We pass 'target_tag' (for data fetching) and 'is_own_country' (for permission/hiding buttons)
        self._render_panels(
            state, 
            target_tag=target_tag, 
            is_own_country=is_own_country,
            selected_region_id=selected_region_id,
            on_focus_request=self._on_focus_region
        )

    def _resolve_active_context(self, state, selected_region_id: Optional[int]) -> tuple[str, bool]:
        """
        Determines which country is currently active in the UI.
        
        Logic:
            - If a region is selected AND it has an owner -> Show that owner.
            - If nothing selected OR ocean -> Show Local Player.
        
        Returns:
            (target_tag, is_own_country)
        """
        # Optimization: Only re-query Polars if selection changed
        if selected_region_id != self._last_selected_id:
            self._last_selected_id = selected_region_id
            
            if selected_region_id is None or selected_region_id <= 0:
                self._cached_target_tag = self.local_player_tag
            else:
                # Lookup owner
                if "regions" in state.tables:
                    df = state.tables["regions"]
                    # Fast single-row filter
                    rows = df.filter(pl.col("id") == selected_region_id)
                    if not rows.is_empty():
                        owner = rows["owner"][0]
                        # If owner is "None" (Neutral/Wasteland), revert to player view
                        self._cached_target_tag = owner if (owner and owner != "None") else self.local_player_tag
                    else:
                        self._cached_target_tag = self.local_player_tag
                else:
                    self._cached_target_tag = self.local_player_tag

        target_tag = self._cached_target_tag
        is_own = (target_tag == self.local_player_tag)
        
        return target_tag, is_own
