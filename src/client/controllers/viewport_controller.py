import arcade
import polars as pl
from typing import Optional, Callable
from enum import Enum, auto

from src.client.controllers.camera_controller import CameraController
from src.client.renderers.map_renderer import MapRenderer
from src.client.services.network_client_service import NetworkClient
from src.client.utils.color_generator import generate_political_colors
from src.client.utils.coords_util import image_to_world

class SelectionMode(Enum):
    REGION = auto()
    COUNTRY = auto()

class ViewportController:
    """
    The Brains of the Map.
    Handles Input -> Camera, Input -> Selection, and State -> Visual Layers.
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
        self.selection_mode = SelectionMode.REGION

    def set_selection_mode(self, mode: SelectionMode):
        """
        Switches between Region and Country selection modes.
        Clears current selection to prevent visual confusion.
        """
        self.selection_mode = mode
        # Clear visual highlight on map
        self.renderer.clear_highlight()
        # Notify UI to clear inspector panel
        self.on_selection_change(None)

    # --- VISUALIZATION HELPERS ---
    def refresh_political_layer(self):
        """
        Fetches state, generates colors, and updates the GPU texture.
        """
        state = self.net.get_state()
        if "regions" not in state.tables: return

        df = state.get_table("regions")
        if "owner" not in df.columns: return

        # 1. Generate Mapping
        region_map = dict(zip(df["id"], df["owner"]))
        unique_owners = df["owner"].unique().to_list()
        
        # 2. Generate Deterministic Colors
        color_map = generate_political_colors(unique_owners)
        
        # 3. Push to GPU
        self.renderer.update_political_layer(region_map, color_map)

    def focus_on_region(self, region_id: int):
        """
        Calculates region center and jumps camera.
        """
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
        elif button in (arcade.MOUSE_BUTTON_RIGHT, arcade.MOUSE_BUTTON_MIDDLE):
            self._is_panning = True

    def on_mouse_release(self, x: float, y: float, button: int):
        if button in (arcade.MOUSE_BUTTON_RIGHT, arcade.MOUSE_BUTTON_MIDDLE):
            self._is_panning = False

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float, buttons: int):
        # Bitwise check for Arcade 3.0
        is_panning_btn = (buttons & arcade.MOUSE_BUTTON_RIGHT) or (buttons & arcade.MOUSE_BUTTON_MIDDLE)
        
        if self._is_panning or is_panning_btn:
            self.cam.pan(dx, dy)
            self.cam.sync_with_arcade(self.world_cam)
            self._is_panning = True

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int):
        self.cam.zoom_scroll(scroll_y)
        self.cam.sync_with_arcade(self.world_cam)

    # --- SELECTION LOGIC ---
    def select_region_by_id(self, region_id: int):
        """Public API for UI to force selection."""
        if region_id is None or region_id <= 0:
            self.renderer.clear_highlight()
            self.on_selection_change(None)
            return
        self._apply_selection_logic(region_id)

    def _handle_click_selection(self, screen_x: float, screen_y: float):
        world_pos = self.world_cam.unproject((screen_x, screen_y))
        region_id = self.renderer.get_region_id_at_world_pos(world_pos.x, world_pos.y)
        self.select_region_by_id(region_id)

    def _apply_selection_logic(self, region_id: int):
        highlight_ids = [region_id]

        # Handle "Select Country" mode logic
        if self.selection_mode == SelectionMode.COUNTRY:
            state = self.net.get_state()
            if "regions" in state.tables:
                df = state.tables["regions"]
                # Find owner of clicked region
                owner_rows = df.filter(pl.col("id") == region_id)
                if not owner_rows.is_empty():
                    owner = owner_rows["owner"][0]
                    if owner and owner != "None":
                        # Get ALL regions by this owner
                        highlight_ids = df.filter(pl.col("owner") == owner)["id"].to_list()

        self.renderer.set_highlight(highlight_ids)
        self.on_selection_change(region_id)