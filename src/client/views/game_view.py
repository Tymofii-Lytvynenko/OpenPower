import arcade
from typing import Optional

from src.shared.config import GameConfig
from src.server.session import GameSession
from src.client.services.network_client_service import NetworkClient
from src.client.services.imgui_service import ImGuiService

# Base Class
from src.client.views.base_view import BaseImGuiView

# Composition Components
from src.client.renderers.map_renderer import MapRenderer
from src.client.ui.layouts.game_layout import GameLayout
from src.client.controllers.camera_controller import CameraController
from src.client.controllers.viewport_controller import ViewportController
from src.client.utils.color_generator import generate_political_colors

class GameView(BaseImGuiView):
    """
    The main Gameplay state.
    Refactored to match EditorView's architecture using Composition.
    """
    
    def __init__(self, session: GameSession, config: GameConfig, player_tag: str):
        super().__init__()
        self.session = session
        self.config = config
        self.player_tag = player_tag
        
        # 1. Services
        self.net = NetworkClient(session)
        self.imgui = ImGuiService(self.window)
        
        # 2. UI Layout
        self.layout = GameLayout(self.net, player_tag)
        
        # 3. Map System 
        # (Fall back to atlas image path if config asset is missing)
        map_path = config.get_asset_path("map/regions.png")
        if not map_path.exists() and session.atlas:
            from pathlib import Path
            map_path = Path(session.atlas.image_path)

        terrain_path = config.get_asset_path("maps/terrain.png")

        self.renderer = MapRenderer(
            map_path=map_path,
            terrain_path=terrain_path,
            cache_dir=config.cache_dir,
            preloaded_atlas=session.atlas 
        )
        
        # 4. Controllers
        self.world_cam = arcade.Camera2D()
        self.cam_ctrl = CameraController(self.renderer.get_center())
        
        self.viewport_ctrl = ViewportController(
            camera_ctrl=self.cam_ctrl,
            world_camera=self.world_cam,
            map_renderer=self.renderer,
            on_selection_change=self.on_selection_changed
        )
        
        self.selected_region_id: Optional[int] = None

    def on_show_view(self):
        self.window.background_color = arcade.color.BLACK
        self.cam_ctrl.sync_with_arcade(self.world_cam)
        self._refresh_political_map()

    def _refresh_political_map(self):
        """Generates country colors using the shared utility."""
        state = self.net.get_state()
        if "regions" not in state.tables: return
        
        df = state.get_table("regions")
        if "owner" not in df.columns: return
        
        region_map = dict(zip(df["id"], df["owner"]))
        unique_owners = df["owner"].unique().to_list()
        
        color_map = generate_political_colors(unique_owners)
        self.renderer.update_political_layer(region_map, color_map)

    def on_selection_changed(self, region_id: int | None):
        """Callback from ViewportController."""
        self.selected_region_id = region_id

    def on_draw(self):
        self.clear()
        self.imgui.new_frame(1.0 / 60.0)
        
        # World Render
        self.world_cam.use()
        self.renderer.draw_map(mode=self.layout.map_mode)
        
        # UI Render
        self.window.use()
        self.layout.render(self.selected_region_id, self.imgui.io.framerate)
        self.imgui.render()

    def on_update(self, delta_time: float):
        # Tick the session (Local Single Player)
        self.session.tick(delta_time)

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