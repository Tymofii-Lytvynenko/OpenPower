import arcade
from typing import Optional, Any
from src.client.services.network_client_service import NetworkClient
from src.client.ui.panels.region_inspector import RegionInspectorPanel
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME

class BaseLayout:
    """
    BaseLayout serves as the foundation for all user interface layouts in the application.
    
    It manages shared UI components that persist across different game states (like 
    the Editor or Live Game) and acts as a bridge between the UI event system 
    and the Viewport/Camera controllers.
    
    Attributes:
        net (NetworkClient): Service for fetching game state and sending commands.
        viewport_ctrl (ViewportController): The controller handling map logic and camera.
        composer (UIComposer): Manages the visual theme and UI element styling.
        inspector (RegionInspectorPanel): The UI panel for viewing specific region details.
    """

    def __init__(self, net_client: NetworkClient, viewport_ctrl: Any):
        """
        Initializes the shared UI infrastructure.

        Args:
            net_client: Instance of the NetworkClient service.
            viewport_ctrl: The controller for the map viewport (ViewportController).
        """
        self.net = net_client
        self.viewport_ctrl = viewport_ctrl
        
        # UIComposer handles theme application (colors, fonts, padding)
        # using the global GAMETHEME configuration.
        self.composer = UIComposer(GAMETHEME)
        
        # Instantiate the Inspector Panel once. 
        # This allows the panel to maintain its internal state (like scroll position 
        # or cached layout data) even when the selected region changes.
        self.inspector = RegionInspectorPanel()

    def render_inspector(self, selected_region_id: Optional[int], state: Any):
        """
        Renders the Region Inspector panel into the current UI frame.

        Args:
            selected_region_id: The ID of the currently selected region (if any).
            state: The current GameState object used to populate panel data.
        """
        # We pass self._on_focus_region as a callback.
        # This allows the Inspector UI to remain "dumb"—it doesn't need to know
        # how to move cameras, it just signals that the user clicked 'Focus'.
        self.inspector.render(
            selected_region_id, 
            state, 
            self._on_focus_region
        )

    def _on_focus_region(self, region_id: int, image_x: float, image_y: float):
        """
        Internal callback triggered when the user clicks 'Focus' in the UI.
        
        This method delegates the coordinate conversion and camera movement 
        to the ViewportController. 

        Args:
            region_id: The unique ID of the region to center on.
            image_x: Raw X coordinate on the map texture (unused here, handled by controller).
            image_y: Raw Y coordinate on the map texture (unused here, handled by controller).
        """
        # DELEGATION: We tell the controller WHICH region to focus on.
        # The controller is responsible for:
        # 1. Looking up the region's center in the data tables.
        # 2. Converting those coordinates to world space.
        # 3. Moving the camera and syncing it with the Arcade engine.
        self.viewport_ctrl.focus_on_region(region_id)