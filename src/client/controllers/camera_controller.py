import arcade
from pyglet.math import Vec2

class CameraController:
    """
    Manages the math behind camera movement and zooming.
    Pure logic class; knows nothing about Mouse Events or Input.
    """
    def __init__(self, start_pos: tuple[float, float]):
        self.ZOOM_SPEED = 0.1
        self.MIN_ZOOM = 0.1
        self.MAX_ZOOM = 5.0

        self.position = Vec2(start_pos[0], start_pos[1])
        self.zoom = 1.0

    def pan(self, dx: float, dy: float):
        """Moves camera based on screen-space drag deltas."""
        scale_factor = 1.0 / self.zoom
        # Invert direction: Dragging RIGHT moves camera LEFT
        movement = Vec2(dx, dy) * scale_factor
        self.position -= movement

    def zoom_scroll(self, scroll_y: int):
        direction = 1.0 if scroll_y > 0 else -1.0
        self.zoom += direction * self.ZOOM_SPEED
        self.zoom = max(self.MIN_ZOOM, min(self.zoom, self.MAX_ZOOM))

    def jump_to(self, x: float, y: float):
        self.position = Vec2(x, y)

    def sync_with_arcade(self, camera: arcade.Camera2D):
        """Applies internal state to the renderer's camera."""
        camera.position = self.position
        camera.zoom = self.zoom