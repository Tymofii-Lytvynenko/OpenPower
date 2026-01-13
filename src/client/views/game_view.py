import arcade
from typing import Optional, TYPE_CHECKING
from pathlib import Path

from src.shared.config import GameConfig
from src.client.services.network_client_service import NetworkClient
from src.client.services.imgui_service import ImGuiService
from src.client.views.base_view import BaseImGuiView

# Components
from src.client.renderers.map_renderer import MapRenderer
from src.client.ui.layouts.game_layout import GameLayout
from src.client.controllers.camera_controller import CameraController
from src.client.controllers.viewport_controller import ViewportController
from src.client.utils.color_generator import generate_political_colors

if TYPE_CHECKING:
    from src.server.session import GameSession

class GameView(BaseImGuiView):
    """
    The main Gameplay state.
    """
    
    def __init__(self, session: "GameSession", config: GameConfig, player_tag: str):
        super().__init__()
        self.config = config
        
        # 1. Services
        # We wrap the session immediately. The rest of the view knows ONLY about self.net
        self.net = NetworkClient(session)
        self.imgui = ImGuiService(self.window)
        
        # 2. UI Layout
        self.layout = GameLayout(self.net, player_tag)
        
        # 3. Map System 
        # UPDATED: We use the session.map_data (Core) directly.
        # We also re-resolve the texture paths for the Renderer (Client).
        
        # Logic: Try to find the same map image the server loaded
        map_path = config.get_asset_path("map/regions.png")
        if not map_path.exists():
            # Fallback attempts
            for data_dir in config.get_data_dirs():
                candidate = data_dir / "regions" / "regions.png"
                if candidate.exists():
                    map_path = candidate
                    break

        terrain_path = config.get_asset_path("map/terrain.png")

        # UPDATED: New Constructor Signature
        self.renderer = MapRenderer(
            map_data=session.map_data, # Core Logic Object (Headless Safe)
            map_img_path=map_path,     # Path for GPU Texture Loading
            terrain_img_path=terrain_path
        )
        
        # 4. Controllers
        self.world_cam = arcade.Camera2D()
        
        # Get center from renderer logic
        center_x, center_y = self.renderer.width / 2, self.renderer.height / 2
        self.cam_ctrl = CameraController((center_x, center_y))
        
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
        """Reads state via NetClient and updates renderer."""
        state = self.net.get_state()
        if "regions" not in state.tables: return
        
        df = state.get_table("regions")
        if "owner" not in df.columns: return
        
        # Efficient Polars to Dict
        region_map = dict(zip(df["id"], df["owner"]))
        unique_owners = df["owner"].unique().to_list()
        
        # Generate colors for dynamic/modded countries
        color_map = generate_political_colors(unique_owners)
        
        self.renderer.update_political_layer(region_map, color_map)

    def on_selection_changed(self, region_id: int | None):
        self.selected_region_id = region_id

    def on_draw(self):
        self.clear()
        self.imgui.new_frame(1.0 / 60.0)
        
        # World Render
        self.world_cam.use()
        
        # UPDATED: map_mode logic is handled by the renderer.draw argument
        mode = "political" if self.layout.map_mode == "political" else "terrain"
        self.renderer.draw(mode=mode)
        
        # UI Render
        self.window.use()
        self.layout.render(self.selected_region_id, self.imgui.io.framerate)
        self.imgui.render()

    # NOTE: No on_update here. The MainWindow drives the session.tick().
    # This View is purely for visualization of that state.

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