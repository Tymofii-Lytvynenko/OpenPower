import arcade

class CameraController:
    """
    Керує логікою зуму та панорамування камери.
    Відповідає логіці Godot: editor_camera.gd
    """
    def __init__(self, start_pos: arcade.math.Vector2):
        # Налаштування (можна винести в constants.py)
        self.ZOOM_SPEED = 0.05
        self.MIN_ZOOM = 0.1
        self.MAX_ZOOM = 5.0

        self.position = start_pos
        self.zoom = 1.0

    def scroll(self, scroll_y: int):
        """Обробка прокрутки коліщатка (Зум)."""
        if scroll_y > 0:
            self.zoom *= (1.0 + self.ZOOM_SPEED)
        elif scroll_y < 0:
            self.zoom *= (1.0 - self.ZOOM_SPEED)
        
        # Clamp
        self.zoom = max(self.MIN_ZOOM, min(self.zoom, self.MAX_ZOOM))

    def drag(self, dx: int, dy: int):
        """Обробка перетягування мишею (Пан)."""
        # position -= event.relative * (1.0 / zoom)
        scale_factor = 1.0 / self.zoom
        self.position.x -= dx * scale_factor
        self.position.y -= dy * scale_factor

    def update_arcade_camera(self, camera: arcade.Camera, window_width: int, window_height: int):
        """Застосовує розраховані параметри до об'єкта arcade.Camera."""
        viewport_w = window_width / self.zoom
        viewport_h = window_height / self.zoom
        
        # Центрування: розраховуємо лівий нижній кут
        left = self.position.x - (viewport_w / 2)
        bottom = self.position.y - (viewport_h / 2)
        
        camera.set_projection(
            left=left,
            right=left + viewport_w,
            bottom=bottom,
            top=bottom + viewport_h
        )

    def screen_to_world(self, screen_x: float, screen_y: float, window_width: int, window_height: int) -> tuple[float, float]:
        """Конвертує координати екрану в координати світу."""
        viewport_w = window_width / self.zoom
        viewport_h = window_height / self.zoom
        
        cam_left = self.position.x - (viewport_w / 2)
        cam_bottom = self.position.y - (viewport_h / 2)
        
        world_x = cam_left + (screen_x / self.zoom)
        world_y = cam_bottom + (screen_y / self.zoom)
        
        return world_x, world_y