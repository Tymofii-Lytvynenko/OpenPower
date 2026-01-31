import arcade
import polars as pl
from typing import Optional, Callable, Dict
from enum import Enum, auto

from src.client.controllers.camera_controller import CameraController
from src.client.renderers.map_renderer import MapRenderer
from src.client.services.network_client_service import NetworkClient
from src.client.utils.coords_util import image_to_world

# Strategy Imports
from src.client.map_modes.base_map_mode import BaseMapMode
from src.client.map_modes.political_mode import PoliticalMapMode
from src.client.map_modes.gradient_mode import GradientMapMode


class SelectionMode(Enum):
    REGION = auto()
    COUNTRY = auto()


class ViewportController:
    """
    The Brains of the Map.
    Handles Input -> Camera, Input -> Selection, and State -> Map Modes.
    """

    def __init__(self,
                 cam_ctrl: CameraController,
                 world_camera: arcade.Camera2D,
                 map_renderer: MapRenderer,
                 net_client: NetworkClient,
                 on_selection_change: Callable[[Optional[int]], None]):

        self.cam = cam_ctrl
        self.world_cam = world_camera
        self.renderer = map_renderer
        self.net = net_client
        self.on_selection_change = on_selection_change

        self._is_panning = False
        self.selection_mode = SelectionMode.COUNTRY

        # --- MAP MODES (Composition) ---
        # We instantiate strategies here. The 'political' mode is default.
        self.map_modes: Dict[str, BaseMapMode] = {
            "political": PoliticalMapMode(),

            # FIXED CONFIGURATION
            "gdp_per_capita": GradientMapMode(
                mode_name="GDP (Per Capita)",
                column_name="gdp_per_capita",
                fallback_to_country=True,
                use_percentile=True,
                steps=10
            ),
            "gvt_stability": GradientMapMode(
                mode_name="Government Stability",
                column_name="gvt_stability",
                fallback_to_country=True,
                use_percentile=True,
                steps=10
            ),
            "money_reserves": GradientMapMode(
                mode_name="Money Reserves",
                column_name="money_reserves",
                fallback_to_country=True,
                use_percentile=True,
                steps=10
            ),
        }
        self.current_mode_key = "political"

    def set_selection_mode(self, mode: SelectionMode):
        self.selection_mode = mode
        self.renderer.clear_highlight()
        self.on_selection_change(None)

    def set_map_mode(self, mode_key: str):
        """
        Public API to switch the active visualization strategy.
        """
        if mode_key in self.map_modes:
            self.current_mode_key = mode_key
            self.refresh_map_layer()

    # --- VISUALIZATION HELPERS ---

    def refresh_map_layer(self):
        """
        Fetches state, asks the active MapMode Strategy to calculate colors,
        and pushes the result to the generic GPU renderer.
        """
        state = self.net.get_state()
        active_mode = self.map_modes[self.current_mode_key]

        # 1. Execute Strategy (Pure Data Transformation)
        color_map = active_mode.calculate_colors(state)

        # 2. Update Renderer (Pure Visualization)
        self.renderer.update_overlay(color_map)

    # Legacy alias for compatibility with older Views, routed to new logic
    def refresh_political_layer(self):
        self.set_map_mode("political")

    def focus_on_region(self, region_id: int):
        state = self.net.get_state()
        if "regions" not in state.tables: return

        df = state.tables["regions"]
        row = df.filter(pl.col("id") == region_id)

        if not row.is_empty():
            cx = row["center_x"][0]
            cy = row["center_y"][0]

            # Convert to World Space
            wx, wy = image_to_world(cx, cy, self.renderer.height)

            # Execute Jump
            self.cam.jump_to(wx, wy)
            self.cam.sync_with_arcade(self.world_cam)

            # Force selection
            self.select_region_by_id(region_id)

    # --- INPUT HANDLING ---
    def on_mouse_press(self, x: float, y: float, button: int):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._handle_click_selection(x, y)

    def on_mouse_release(self, x: float, y: float, button: int):
        pass

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float, buttons: int):
        # Globe rotation is handled by MapRenderer (LMB drag).
        # Keep RMB/MMB panning disabled in globe mode for now.
        pass

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int):
        # Globe zoom
        self.renderer.on_mouse_scroll(x, y, scroll_x, scroll_y)

    # --- SELECTION LOGIC ---
    def select_region_by_id(self, region_id: int):
        if region_id is None or region_id <= 0:
            self.renderer.clear_highlight()
            self.on_selection_change(None)
            return
        self._apply_selection_logic(region_id)

    def _handle_click_selection(self, screen_x: float, screen_y: float):
        # Globe: pick directly in screen space (raycast)
        region_id = self.renderer.get_region_id_at_screen_pos(screen_x, screen_y)
        self.select_region_by_id(region_id)

    def _apply_selection_logic(self, region_id: int):
        highlight_ids = [region_id]

        if self.selection_mode == SelectionMode.COUNTRY:
            state = self.net.get_state()
            if "regions" in state.tables:
                df = state.tables["regions"]
                # Find owner of clicked region
                owner_rows = df.filter(pl.col("id") == region_id)
                if not owner_rows.is_empty():
                    owner = owner_rows["owner"][0]
                    if owner and owner != "None":
                        # Get ALL regions by this owner for multi-select
                        highlight_ids = df.filter(pl.col("owner") == owner)["id"].to_list()

        self.renderer.set_highlight(highlight_ids)
        self.on_selection_change(region_id)

    def get_region_at(self, screen_x: float, screen_y: float) -> Optional[int]:
        try:
            region_id = self.renderer.get_region_id_at_screen_pos(screen_x, screen_y)
            return region_id if region_id > 0 else None
        except Exception:
            return None
