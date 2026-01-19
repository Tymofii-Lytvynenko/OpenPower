import arcade
from src.shared.config import GameConfig
from src.client.services.network_client_service import NetworkClient
from src.client.services.imgui_service import ImGuiService
from src.client.views.base_view import BaseImGuiView

from src.client.renderers.map_renderer import MapRenderer
from src.client.ui.layouts.game_layout import GameLayout
from src.client.controllers.camera_controller import CameraController
from src.client.controllers.viewport_controller import ViewportController
from src.client.utils.color_generator import generate_political_colors
from src.client.ui.theme import GAMETHEME

class GameView(BaseImGuiView):
    # FIX 1: Update type hint to accept None (tuple[...] | None)
    def __init__(self, session, config, player_tag, initial_pos: tuple[float, float] | None = None):
        super().__init__()
        self.config = config
        self.net = NetworkClient(session)
        
        # FIX 2: Explicitly annotate type here so Pylance knows it's not None anymore
        self.imgui: ImGuiService = ImGuiService(self.window)
        
        map_path = config.get_asset_path("map/regions.png")
        terrain_path = config.get_asset_path("map/terrain.png")

        self.renderer = MapRenderer(
            map_data=session.map_data,
            map_img_path=map_path,
            terrain_img_path=terrain_path
        )
        
        self.world_cam = arcade.Camera2D()
 
        if initial_pos:
            start_x, start_y = initial_pos
        else:
            start_x = self.renderer.width / 2
            start_y = self.renderer.height / 2
            
        self.cam_ctrl = CameraController((start_x, start_y))
        
        self.viewport_ctrl = ViewportController(
            cam_ctrl=self.cam_ctrl,
            world_camera=self.world_cam,
            map_renderer=self.renderer,
            net_client=self.net,
            on_selection_change=self.on_selection_changed
        )
        
        self.layout = GameLayout(self.net, player_tag, self.viewport_ctrl)
        self.selected_region_id = None

    def on_show_view(self):
        self.window.background_color = GAMETHEME.col_black
        self.cam_ctrl.sync_with_arcade(self.world_cam)
        self._refresh_political_map()

    def _refresh_political_map(self):
        state = self.net.get_state()
        if "regions" not in state.tables: return
        df = state.get_table("regions")
        region_map = dict(zip(df["id"], df["owner"]))
        unique_owners = df["owner"].unique().to_list()
        color_map = generate_political_colors(unique_owners)
        self.renderer.update_political_layer(region_map, color_map)

    def on_selection_changed(self, region_id: int | None):
        self.selected_region_id = region_id

    def on_draw(self):
        self.clear()
        
        # 1. Start ImGui frame
        self.imgui.new_frame()
        
        # 2. Draw World
        self.world_cam.use()
        mode = "political" if self.layout.map_mode == "political" else "terrain"
        self.renderer.draw(mode=mode)
        
        # 3. Draw UI
        self.window.use()
        self.layout.render(self.selected_region_id, self.imgui.io.framerate)
        
        self.imgui.render()

    # --- IMPLEMENTING BASE HOOKS ---
    def on_game_resize(self, width, height):
        self.world_cam.match_window()

    def on_game_mouse_press(self, x, y, button, modifiers):
        self.viewport_ctrl.on_mouse_press(x, y, button)

    def on_game_mouse_release(self, x, y, button, modifiers):
        self.viewport_ctrl.on_mouse_release(x, y, button)

    def on_game_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        self.viewport_ctrl.on_mouse_drag(x, y, dx, dy, buttons)

    def on_game_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self.viewport_ctrl.on_mouse_scroll(x, y, scroll_x, scroll_y)