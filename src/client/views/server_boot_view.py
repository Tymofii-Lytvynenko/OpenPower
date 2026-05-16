import arcade
from imgui_bundle import imgui

from src.client.views.base_view import BaseImGuiView
from src.client.ui.core.composer import UIComposer
from src.client.ui.core.theme import GAMETHEME


class ServerBootView(BaseImGuiView):
    """Visible startup screen while the multiprocessing simulation server boots."""

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.ui = UIComposer(GAMETHEME)

    def on_show_view(self):
        self.window.background_color = (10, 10, 10, 255)

    def on_game_update(self, delta_time: float):
        self.imgui.update_time(delta_time)

    def on_draw(self):
        self.clear()
        self.imgui.new_frame()
        self.ui.setup_frame()

        progress = float(getattr(self.window, "boot_progress", 0.0))
        status = str(getattr(self.window, "boot_status", "Starting engine..."))
        error = getattr(self.window, "boot_error", None)

        screen_w, screen_h = self.window.get_size()
        if self.ui.begin_centered_panel("Server Boot", screen_w, screen_h, w=460, h=170):
            self.ui.draw_title("OPENPOWER")
            self.ui.draw_progress_bar(progress, status)

            if error:
                imgui.text_colored(GAMETHEME.colors.error, str(error))
            else:
                imgui.text_disabled("Starting simulation process...")

            self.ui.end_panel()

        self.imgui.render()
