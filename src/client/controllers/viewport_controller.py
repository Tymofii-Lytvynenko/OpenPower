import arcade
from typing import Optional, Callable
from src.client.controllers.camera_controller import CameraController
from src.client.renderers.map_renderer import MapRenderer

class ViewportController:
    """
    Mediator between Raw Input, the Camera, and the Map Renderer.
    Responsibility: 'What happens when I click the map?'
    """
    def __init__(self, 
                 camera_ctrl: CameraController, 
                 world_camera: arcade.Camera2D,
                 map_renderer: MapRenderer,
                 on_selection_change: Callable[[Optional[int]], None]):
        
        self.cam_ctrl = camera_ctrl
        self.world_cam = world_camera
        self.renderer = map_renderer
        self.on_selection_change = on_selection_change
        
        # Internal state to track panning (useful for logic that doesn't provide button state)
        self._is_panning = False

    def on_mouse_press(self, x: float, y: float, button: int):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._handle_selection(x, y)
        elif button in (arcade.MOUSE_BUTTON_RIGHT, arcade.MOUSE_BUTTON_MIDDLE):
            self._is_panning = True

    def on_mouse_release(self, x: float, y: float, button: int):
        if button in (arcade.MOUSE_BUTTON_RIGHT, arcade.MOUSE_BUTTON_MIDDLE):
            self._is_panning = False

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float, buttons: int):
        """
        Handles camera panning.
        We check both the internal flag AND the physical button state.
        This fixes the bug where ImGui swallows the initial 'Press' event 
        (e.g., closing a dropdown), leaving _is_panning False while dragging.
        """
        # Check if Right (4) or Middle (2) button is physically held down
        # 'buttons' is a bitmask in Arcade 3.0
        is_right_held = buttons & arcade.MOUSE_BUTTON_RIGHT
        is_middle_held = buttons & arcade.MOUSE_BUTTON_MIDDLE
        
        if self._is_panning or is_right_held or is_middle_held:
            self.cam_ctrl.pan(dx, dy)
            self.cam_ctrl.sync_with_arcade(self.world_cam)

            # Ensure state remains consistent if we recovered from a missed click
            self._is_panning = True

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int):
        self.cam_ctrl.zoom_scroll(scroll_y)
        self.cam_ctrl.sync_with_arcade(self.world_cam)

    def _handle_selection(self, screen_x: float, screen_y: float):
        """
        Translates screen click to world map selection.
        """
        world_pos = self.world_cam.unproject((screen_x, screen_y))
        
        # Query the renderer (which checks the Atlas)
        region_id = self.renderer.get_region_id_at_world_pos(world_pos.x, world_pos.y)
        
        # Update Visuals
        if region_id is not None:
            self.renderer.set_highlight([region_id])
        else:
            self.renderer.clear_highlight()
            
        # Notify the View/UI
        self.on_selection_change(region_id)