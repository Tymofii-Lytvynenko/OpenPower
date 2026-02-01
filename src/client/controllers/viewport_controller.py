import arcade
import polars as pl
from typing import Optional, Callable, Dict
from enum import Enum, auto

from src.client.controllers.camera_controller import CameraController
from src.client.renderers.map_renderer import MapRenderer
from src.client.services.network_client_service import NetworkClient

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

        self.selection_mode = SelectionMode.COUNTRY

        # --- MAP MODES (Composition) ---
        self.map_modes: Dict[str, BaseMapMode] = {
            "political": PoliticalMapMode(),
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
        if mode_key in self.map_modes:
            self.current_mode_key = mode_key
            self.refresh_map_layer()

    # --- VISUALIZATION HELPERS ---

    def refresh_map_layer(self):
        state = self.net.get_state()
        active_mode = self.map_modes[self.current_mode_key]
        color_map = active_mode.calculate_colors(state)

        self.renderer.set_overlay_style(
            enabled=active_mode.overlay_enabled,
            opacity=active_mode.opacity
        )
        self.renderer.update_overlay(color_map)

    def refresh_political_layer(self):
        self.set_map_mode("political")

    def focus_on_region(self, region_id: int):
        """Finds a region and rotates the globe to face it."""
        state = self.net.get_state()
        if "regions" not in state.tables: return

        df = state.tables["regions"]
        row = df.filter(pl.col("id") == region_id)

        if not row.is_empty():
            cx = row["center_x"][0]
            cy = row["center_y"][0]

            # Use the new 3D method
            self.cam.look_at_pixel_coords(
                cx, cy, 
                self.renderer.width, 
                self.renderer.height
            )
            
            # Force selection
            self.select_region_by_id(region_id)

    # --- INPUT HANDLING ---
    
    def on_mouse_press(self, x: float, y: float, button: int):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._handle_click_selection(x, y)

    def on_mouse_release(self, x: float, y: float, button: int):
        pass

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float, buttons: int):
        # Handle 3D rotation via the controller
        if buttons & arcade.MOUSE_BUTTON_LEFT:
            self.cam.drag(dx, dy)

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int):
        # Handle 3D zoom via the controller
        self.cam.zoom_scroll(scroll_y)

    # --- SELECTION LOGIC ---
    def select_region_by_id(self, region_id: int):
        if region_id is None or region_id <= 0:
            self.renderer.clear_highlight()
            self.on_selection_change(None)
            return
        self._apply_selection_logic(region_id)

    def _handle_click_selection(self, screen_x: float, screen_y: float):
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