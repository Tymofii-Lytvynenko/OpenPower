import arcade
from src.server.session import GameSession
from src.shared.config import GameConfig
from src.client.views.editor_view import EditorView

class MainWindow(arcade.Window):
    def __init__(self, session: GameSession, config: GameConfig):
        super().__init__(1280, 720, "OpenPower Editor", resizable=True)
        self.session = session
        self.game_config = config
        self.center_window()

    def setup(self):
        print("[Window] Initializing...")
        start_view = EditorView(self.session, self.game_config)
        self.show_view(start_view)
        
    def on_update(self, delta_time: float):
        self.session.tick(delta_time)