import arcade
from src.client.views.editor_view import EditorView

# Конфігурація вікна
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
SCREEN_TITLE = "OpenPower Engine"

class MainWindow(arcade.Window):
    """
    Головне вікно програми.
    Діє як контейнер для Views (Редактор, Гра, Меню).
    """
    def __init__(self):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE, resizable=True)
        
    def setup(self):
        """Ініціалізація та запуск стартової сцени."""
        # Тут ми можемо додати аргументи командного рядка для вибору режиму
        # Але поки що за замовчуванням запускаємо EditorView
        start_view = EditorView()
        self.show_view(start_view)

    def on_resize(self, width, height):
        """Передаємо подію зміни розміру активній сцені."""
        super().on_resize(width, height)
        # Примітка: arcade.Window автоматично викликає on_resize для поточної View,
        # але іноді корисно мати явний контроль.