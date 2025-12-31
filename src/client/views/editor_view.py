import arcade
from pathlib import Path

# Імпорти компонентів (переконайтеся, що файли існують з попередніх кроків)
from src.client.camera_controller import CameraController
from src.client.renderers.map_renderer import MapRenderer

# Константи (можна винести в окремий файл конфігу пізніше)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MAP_PATH = PROJECT_ROOT / "modules" / "base" / "assets" / "maps" / "provinces.png"

class EditorView(arcade.View):
    """
    Режим Редактора (Editor Mode).
    Відповідає за інструменти редагування мапи, сценаріїв та даних.
    """
    def __init__(self):
        super().__init__()
        
        # Компоненти
        self.camera_controller = None
        self.map_renderer = None
        
        # Камери
        self.world_camera = None
        self.ui_camera = None

    def setup(self):
        """Ініціалізація ресурсів сцени."""
        # Отримуємо розміри вікна
        width = self.window.width
        height = self.window.height
        
        self.world_camera = arcade.Camera(width, height)
        self.ui_camera = arcade.Camera(width, height)
        
        # Ініціалізація рендерера мапи
        self.map_renderer = MapRenderer(MAP_PATH)
        
        # Ініціалізація контролера камери
        # Центруємо на мапі, якщо вона завантажилась, інакше (0,0)
        start_pos = self.map_renderer.get_center()
        self.camera_controller = CameraController(start_pos)
        
        # Перше оновлення
        self.camera_controller.update_arcade_camera(self.world_camera, width, height)
        print("[EditorView] Setup complete.")

    def on_show_view(self):
        """Викликається, коли ця сцена стає активною."""
        self.setup()
        # Встановлюємо сірий фон для редактора, щоб відрізняти від гри
        self.window.background_color = arcade.color.DARK_SLATE_GRAY

    def on_draw(self):
        """Рендеринг."""
        self.clear()
        
        # 1. Шар світу
        self.world_camera.use()
        if self.map_renderer:
            self.map_renderer.draw()
            
        # 2. Шар UI
        self.ui_camera.use()
        # Тимчасова налагоджувальна інформація
        arcade.draw_text("EDITOR MODE", 10, self.window.height - 30, arcade.color.WHITE, 20)
        arcade.draw_text("Controls: Scroll to Zoom, Middle Click to Pan, Left Click to Select", 
                         10, self.window.height - 60, arcade.color.WHITE, 12)

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._handle_selection(x, y)

    def _handle_selection(self, screen_x: int, screen_y: int):
        # Конвертуємо координати
        wx, wy = self.camera_controller.screen_to_world(
            screen_x, screen_y, self.window.width, self.window.height
        )
        
        # Отримуємо колір
        color_hex = self.map_renderer.get_color_at_world_pos(wx, wy)
        
        if color_hex:
            if color_hex not in ["#ffffff", "#000000"]:
                print(f"[Editor] Region Selected: {color_hex}")
            else:
                print("[Editor] Clicked border")

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self.camera_controller.scroll(scroll_y)
        self.camera_controller.update_arcade_camera(
            self.world_camera, self.window.width, self.window.height
        )

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if buttons == arcade.MOUSE_BUTTON_MIDDLE:
            self.camera_controller.drag(dx, dy)
            self.camera_controller.update_arcade_camera(
                self.world_camera, self.window.width, self.window.height
            )

    def on_resize(self, width, height):
        self.world_camera.resize(width, height)
        self.ui_camera.resize(width, height)
        if self.camera_controller:
            self.camera_controller.update_arcade_camera(self.world_camera, width, height)