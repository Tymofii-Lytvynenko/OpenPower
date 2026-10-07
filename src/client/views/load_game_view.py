import arcade

from src.client.views.base_view import BaseImGuiView
from src.client.ui.core.composer import UIComposer
from src.client.ui.core.theme import GAMETHEME
from src.shared.config import GameConfig
from src.core.saves import list_available_saves


class LoadGameView(BaseImGuiView):
    def __init__(self, config: GameConfig):
        super().__init__()
        self.config = config

        # UI Composer (ImGuiService is handled by BaseImGuiView)
        self.ui = UIComposer(GAMETHEME)

        # Populate save list using the layer-agnostic core helper — no server imports needed.
        self.save_list = list_available_saves(config)
        self.selected_save_name = None

    def on_show_view(self):
        self.window.background_color = arcade.color.BLACK
        if not self.imgui:
            self.setup_imgui()

    def on_draw(self):
        self.clear()

        self.imgui.new_frame()
        self.ui.setup_frame()

        screen_w, screen_h = self.window.get_size()

        if self.ui.begin_centered_panel("Load Game", screen_w, screen_h, w=500, h=600):
            self.ui.draw_title("LOAD GAME")
            from imgui_bundle import imgui

            # --- Save List ---
            imgui.begin_child("SaveList", (0, 400), True)
            if not self.save_list:
                imgui.text_disabled("No saves found.")
            else:
                for save in self.save_list:
                    name = save['name']
                    date = save['timestamp'][:16].replace("T", " ")
                    label = f"{name}  |  {date}"
                    if imgui.selectable(label, self.selected_save_name == name)[0]:
                        self.selected_save_name = name
            imgui.end_child()
            imgui.dummy((0, 20))

            # --- Buttons ---

            # BACK BUTTON: Use Router
            if imgui.button("BACK", (100, 40)):
                current_session = getattr(self.window, 'session', None)
                self.nav.show_main_menu(current_session, self.config)

            imgui.same_line()
            avail_w = imgui.get_content_region_avail().x
            imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + avail_w - 150)

            if self.selected_save_name:
                if imgui.button("LOAD", (150, 40)):
                    self._load_selected_save()
            else:
                imgui.begin_disabled()
                imgui.button("LOAD", (150, 40))
                imgui.end_disabled()

            self.ui.end_panel()

            self.imgui.render()

    def _load_selected_save(self):
        print(f"Loading {self.selected_save_name}...")
        from src.client.tasks.load_game_task import LoadGameTask

        task = LoadGameTask(self.window, self.config, self.selected_save_name)

        def on_success(session):
            self.window.session = session
            state = session.get_state_snapshot()
            player_tag = "USA"
            if state and state.globals:
                player_tag = state.globals.get("player_tag", "USA")

            self.nav.show_game_view(session, self.config, player_tag)
            return None

        self.nav.show_loading(task, on_success)
