# --- File: ui/layouts/game_layout.py ---
from typing import Optional

# Third-party imports
# (Standard imports required for type hinting and UI logic)
import arcade 

# Internal - UI & Theme
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME
from src.client.services.network_client_service import NetworkClient

# Internal - Components (HUD Bars)
# We delegate specific UI sections to dedicated components to adhere to 
# the Single Responsibility Principle and Composition over Inheritance (CoI).
from src.client.ui.components.hud.central_bar import CentralBar
from src.client.ui.components.hud.system_bar import SystemBar
from src.client.ui.components.hud.toggle_bar import ToggleBar

# Internal - Panels
# These are the specialized content windows for game mechanics.
from src.client.ui.layouts.base_layout import BaseLayout
from src.client.ui.panels.politics_panel import PoliticsPanel
from src.client.ui.panels.military_panel import MilitaryPanel
from src.client.ui.panels.economy_panel import EconomyPanel
from src.client.ui.panels.demographics_panel import DemographicsPanel
from src.client.ui.panels.data_insp_panel import DataInspectorPanel

class GameLayout(BaseLayout):
    """
    The primary HUD Layout for the Gameplay View.

    This class acts as the 'Director' of the UI composition. It does not handle 
    the specific rendering logic of buttons or bars; instead, it orchestrates 
    the placement and updates of sub-components (SystemBar, CentralBar, Panels).
    """

    def __init__(self, net_client: NetworkClient, player_tag: str, viewport_ctrl):
        """
        Initialize the layout and register all interactive panels.
        
        Args:
            net_client: Service for communicating with the server (fetching state).
            player_tag: The ID of the country the player is currently viewing (e.g., 'USA').
            viewport_ctrl: Controller for map camera interactions (zooming, focusing).
        """
        super().__init__(net_client, viewport_ctrl)
        
        self.player_tag = player_tag
        
        # We store map mode state here to allow specific menu toggles (like "Map Mode") 
        # to persist across frames.
        self.map_mode = "political"

        # --- Panel Registry ---
        # Panels are registered with an ID, instance, and optional metadata (icon/color).
        # This metadata is used by the ToggleBar to generate buttons dynamically.
        self.register_panel("POL", PoliticsPanel(), icon="POL", color=GAMETHEME.col_politics, visible=False)
        self.register_panel("MIL", MilitaryPanel(), icon="MIL", color=GAMETHEME.col_military, visible=False)
        self.register_panel("ECO", EconomyPanel(), icon="ECO", color=GAMETHEME.col_economy, visible=False)
        self.register_panel("DEM", DemographicsPanel(), icon="DEM", color=GAMETHEME.col_demographics, visible=False)
        
        # Debug/Inspector tools (No icon, accessed via context menu)
        self.register_panel("DATA_INSPECTOR", DataInspectorPanel(), visible=False)

        # --- HUD Components ---
        # Initialize the persistent bar components. 
        # These maintain their own internal state (like animation timers or cache).
        self.central_bar = CentralBar()
        self.system_bar = SystemBar()
        self.toggle_bar = ToggleBar()

    def render(self, selected_region_id: Optional[int], fps: float, nav_service):
        """
        The Main UI Render Loop.
        
        This is called every frame by the GameView. It sets up the ImGui frame,
        fetches the latest game state, and delegates rendering to sub-components.

        Args:
            selected_region_id: The currently selected map region (if any).
            fps: Current frames per second for the overlay.
            nav_service: The navigation service to handle scene transitions (e.g., Load Game).
        """
        # 1. Prepare standard UI styles (colors, spacing)
        self.composer.setup_frame()
        
        # 2. Fetch the latest snapshot of the game simulation
        # We do this once per frame to ensure all panels see consistent data.
        state = self.net.get_state()

        # 3. Render Global Overlays (Inherited from BaseLayout)
        self._render_fps_counter(fps)
        self._render_context_menu()

        # 4. Render HUD Bars (Modular Components)
        # The System Bar handles global actions (Save/Load/Exit)
        self.system_bar.render(self.composer, self.net, nav_service)
        
        # The Toggle Bar controls the visibility of the panels registered in __init__
        self.toggle_bar.render(self.composer, self.panels)
        
        # The Central Bar displays critical status (Flag, Date, Speed) and can 
        # change the active viewpoint (player_tag) via debug selectors.
        self.player_tag = self.central_bar.render(
            self.composer, 
            state, 
            self.net, 
            self.player_tag
        )

        # 5. Render Interactive Panels
        # Iterate through registered panels and render them if visible.
        # We pass the 'on_focus_request' callback so panels can tell the camera where to look.
        self._render_panels(
            state, 
            player_tag=self.player_tag, 
            selected_region_id=selected_region_id,
            on_focus_request=self._on_focus_region
        )