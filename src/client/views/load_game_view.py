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

        class SaveLoadTask:
            def __init__(self, window, config, save_name):
                self.window = window
                self.config = config
                self.save_name = save_name
                self.progress = 0.0
                self.status_text = "Preparing to load..."

            def run(self):
                import time
                # 1. Shut down existing session proxy if it exists
                self.status_text = "Stopping current simulation..."
                self.progress = 0.1
                if hasattr(self.window, "session") and self.window.session:
                    self.window.session.shutdown()

                # 2. Spawn a new server process via the launcher factory
                self.status_text = f"Initializing load for {self.save_name}..."
                self.progress = 0.2
                from src.server.launcher import spawn_local_server
                from src.client.client_session import ClientSessionProxy
                bundle = spawn_local_server(self.config, save_name=self.save_name)
                new_session = ClientSessionProxy(
                    map_data=bundle.map_data,
                    action_queue=bundle.action_queue,
                    state_queue=bundle.state_queue,
                    progress_queue=bundle.progress_queue,
                    process=bundle.process,
                )

                # 3. Read progress from new_session.progress_queue
                while True:
                    try:
                        status, p, text = new_session.progress_queue.get(timeout=10.0)
                        if status == "PROGRESS":
                            self.progress = 0.2 + p * 0.6
                            self.status_text = f"Server: {text}"
                        elif status == "READY":
                            self.progress = 0.8
                            self.status_text = "Server process ready."
                            break
                        elif status == "ERROR":
                            raise RuntimeError(text)
                    except Exception as e:
                        raise RuntimeError(f"Failed to initialize simulation server for loading: {e}")

                # 4. Wait for first state update
                self.status_text = "Synchronizing game state..."
                self.progress = 0.9

                start_time = time.perf_counter()
                while new_session.get_state_snapshot() is None:
                    new_session.tick(0.0)
                    if time.perf_counter() - start_time > 5.0:
                        raise TimeoutError("Timed out waiting for loaded game state.")
                    time.sleep(0.05)

                self.progress = 1.0
                self.status_text = "Ready."
                return new_session

        task = SaveLoadTask(self.window, self.config, self.selected_save_name)

        def on_success(session):
            self.window.session = session
            state = session.get_state_snapshot()
            player_tag = "USA"
            if state and state.globals:
                player_tag = state.globals.get("player_tag", "USA")

            self.nav.show_game_view(session, self.config, player_tag)
            return None

        self.nav.show_loading(task, on_success)