import arcade
import orjson

# Base Class
from src.client.views.base_view import BaseImGuiView

from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME
from src.shared.config import GameConfig
from src.server.io.save_writer import SaveWriter
from src.server.io.data_load_manager import DataLoader

class LoadGameView(BaseImGuiView):
    def __init__(self, config: GameConfig):
        super().__init__()
        self.config = config
        
        # UI Composer (ImGuiService is handled by BaseImGuiView)
        self.ui = UIComposer(GAMETHEME)
        
        # Initialize Save Helpers
        self.writer = SaveWriter(config)
        self.loader = DataLoader(config)
        
        self.save_list = self.writer.get_available_saves()
        self.selected_save_name = None

    def on_show_view(self):
        self.window.background_color = GAMETHEME.colors.black
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
                # Get session from window if it exists, or None
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
        
        # Define Task Local Class (No top-level imports needed)
        class SaveLoadTask:
            def __init__(self, config, save_name, loader):
                self.config = config
                self.save_name = save_name
                self.loader = loader
                self.progress = 0.0
                self.status_text = "Loading Save..."

            def run(self):
                # ... (Same logic as before, local imports inside here are safe) ...
                self.status_text = "Reading State from Disk..."
                self.progress = 0.3
                loaded_state = self.loader.load_save(self.save_name)
                
                self.status_text = "Initializing Engine..."
                self.progress = 0.6
                
                # Local imports to build session
                from src.server.session import GameSession
                from src.server.io.data_export_manager import DataExporter
                from src.engine.simulator import Engine
                from src.engine.mod_manager import ModManager
                from src.core.map_data import RegionMapData
                
                exporter = DataExporter(self.config)
                engine = Engine()
                mod_mgr = ModManager(self.config)
                
                mods = mod_mgr.resolve_load_order()
                systems = mod_mgr.load_systems()
                engine.register_systems(systems)
                
                map_path = self.config.get_asset_path("map/regions.png")
                map_data = RegionMapData(str(map_path))
                
                session = GameSession(
                    self.config, self.loader, exporter, engine, map_data, loaded_state
                )
                self.progress = 1.0
                return session

        task = SaveLoadTask(self.config, self.selected_save_name, self.loader)
        
        # Callback to handle success
        def on_success(session):
            player_tag = session.state.globals.get("player_tag", "USA") 
            
            # USE ROUTER: Switch to GameView
            self.nav.show_game_view(session, self.config, player_tag)
            
            # Return None to tell LoadingView we handled the transition
            return None

        # USE ROUTER: Switch to LoadingView
        self.nav.show_loading(task, on_success)