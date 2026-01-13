import arcade
import polars as pl
from typing import Optional, Callable
from enum import Enum, auto

from src.client.controllers.camera_controller import CameraController
from src.client.renderers.map_renderer import MapRenderer
from src.client.services.network_client_service import NetworkClient

class SelectionMode(Enum):
    REGION = auto()
    COUNTRY = auto()

class ViewportController:
    """
    Mediator between Raw Input, the Camera, and the Map Renderer.
    """
    def __init__(self, 
                 camera_ctrl: CameraController, 
                 world_camera: arcade.Camera2D,
                 map_renderer: MapRenderer,
                 net_client: NetworkClient,
                 on_selection_change: Callable[[Optional[int]], None]):
        
        self.cam_ctrl = camera_ctrl
        self.world_cam = world_camera
        self.renderer = map_renderer
        self.net = net_client
        self.on_selection_change = on_selection_change
        
        self._is_panning = False
        self.selection_mode = SelectionMode.REGION

    def set_selection_mode(self, mode: SelectionMode):
        self.selection_mode = mode
        self.renderer.clear_highlight() 
        self.on_selection_change(None)

    def on_mouse_press(self, x: float, y: float, button: int):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._handle_selection(x, y)
        elif button in (arcade.MOUSE_BUTTON_RIGHT, arcade.MOUSE_BUTTON_MIDDLE):
            self._is_panning = True

    def on_mouse_release(self, x: float, y: float, button: int):
        if button in (arcade.MOUSE_BUTTON_RIGHT, arcade.MOUSE_BUTTON_MIDDLE):
            self._is_panning = False

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float, buttons: int):
        is_right_held = buttons & arcade.MOUSE_BUTTON_RIGHT
        is_middle_held = buttons & arcade.MOUSE_BUTTON_MIDDLE
        
        if self._is_panning or is_right_held or is_middle_held:
            self.cam_ctrl.pan(dx, dy)
            self.cam_ctrl.sync_with_arcade(self.world_cam)
            self._is_panning = True

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int):
        self.cam_ctrl.zoom_scroll(scroll_y)
        self.cam_ctrl.sync_with_arcade(self.world_cam)

    def _handle_selection(self, screen_x: float, screen_y: float):
        world_pos = self.world_cam.unproject((screen_x, screen_y))
        
        # 1. Get Region ID from Map Data (CPU)
        region_id = self.renderer.get_region_id_at_world_pos(world_pos.x, world_pos.y)
        
        if region_id is None or region_id <= 0:
            self.renderer.clear_highlight()
            self.on_selection_change(None)
            return

        # 2. Determine which IDs to highlight based on mode
        highlight_ids = [region_id]

        if self.selection_mode == SelectionMode.COUNTRY:
            state = self.net.get_state()
            if "regions" in state.tables:
                try:
                    df = state.tables["regions"]
                    # Find owner of the clicked region
                    owner_rows = df.filter(pl.col("id") == region_id)
                    
                    if not owner_rows.is_empty():
                        owner = owner_rows["owner"][0]
                        # If it's a valid country, select ALL regions with that owner
                        if owner and owner != "None":
                            highlight_ids = df.filter(pl.col("owner") == owner)["id"].to_list()
                except Exception as e:
                    print(f"[Viewport] Selection Error: {e}")

        # 3. Update Renderer Visuals
        self.renderer.set_highlight(highlight_ids)
        
        # 4. Update UI Panel (Show info for the specific clicked region)
        self.on_selection_change(region_id)