import arcade
from pyglet.math import Vec2

class CameraController:
    """
    Manages camera zoom and pan logic for the Editor.
    Uses pyglet.math.Vec2 for vector arithmetic.
    """

    def __init__(self, start_pos: tuple[float, float]):
        self.ZOOM_SPEED = 0.05
        self.MIN_ZOOM = 0.1
        self.MAX_ZOOM = 5.0

        # Create a Vector from the tuple
        self.position = Vec2(start_pos[0], start_pos[1])
        self.zoom = 1.0

    def scroll(self, scroll_y: int):
        """Processes mouse wheel events for zooming."""
        if scroll_y > 0:
            self.zoom *= (1.0 + self.ZOOM_SPEED)
        elif scroll_y < 0:
            self.zoom *= (1.0 - self.ZOOM_SPEED)
        
        self.zoom = max(self.MIN_ZOOM, min(self.zoom, self.MAX_ZOOM))

    def drag(self, dx: int, dy: int):
        """Updates the camera position based on mouse drag movement."""
        scale_factor = 1.0 / self.zoom
        
        # Vec2 supports direct subtraction/multiplication
        movement = Vec2(dx, dy) * scale_factor
        self.position -= movement

    def update_arcade_camera(self, camera: arcade.Camera2D):
        """Syncs the internal state with the Arcade Camera2D object."""
        camera.position = self.position
        camera.zoom = self.zoom

    def screen_to_world(self, screen_x: float, screen_y: float, window_width: int, window_height: int) -> tuple[float, float]:
        """Converts screen-space mouse coordinates to absolute world-space coordinates."""
        viewport_w = window_width / self.zoom
        viewport_h = window_height / self.zoom
        
        cam_left = self.position.x - (viewport_w / 2)
        cam_bottom = self.position.y - (viewport_h / 2)
        
        world_x = cam_left + (screen_x / self.zoom)
        world_y = cam_bottom + (screen_y / self.zoom)
        
        return world_x, world_y