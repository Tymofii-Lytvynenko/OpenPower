import arcade

from src.client.views.base_view import BaseImGuiView
from src.client.ui.core.composer import UIComposer
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.components.shared.generic_message_dialog import GenericMessageDialog
from src.client.ui.components.shared.save_game_dialog import SaveGameDialog
from src.core.saves import list_available_saves
from src.shared.config import GameConfig


class LoadGameView(BaseImGuiView):
    def __init__(self, config: GameConfig):
        super().__init__()
        self.config = config

        self.ui = UIComposer(GAMETHEME)
        self.message_dialog = GenericMessageDialog()
        self.load_dialog = SaveGameDialog(
            lambda: list_available_saves(config),
            lambda _name: None,
            self._load_selected_save,
            self.message_dialog.enqueue,
            # Closing this standalone view's source frame must restore its menu.
            on_close=self._return_to_main_menu,
        )
        self.load_dialog.toggle("load")

    def on_show_view(self):
        self.window.background_color = arcade.color.BLACK
        if not self.imgui:
            self.setup_imgui()

    def on_draw(self):
        self.clear()

        self.imgui.new_frame()
        self.ui.setup_frame()
        self.load_dialog.render()
        self.message_dialog.render()
        self.imgui.render()

    def _load_selected_save(self, save_name: str) -> None:
        self.nav.load_saved_game(self.config, save_name)

    def _return_to_main_menu(self) -> None:
        current_session = getattr(self.window, "session", None)
        self.nav.show_main_menu(current_session, self.config)
