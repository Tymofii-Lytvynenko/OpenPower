import arcade
import time
from typing import Optional

from src.shared.config import GameConfig
from src.server.session import GameSession
from src.client.services.network_client_service import NetworkClient
from src.client.services.imgui_service import ImGuiService
from src.client.renderers.map_renderer import MapRenderer
from src.client.camera_controller import CameraController
from src.client.ui.game_layout import GameLayout

class GameView(arcade.View):
    """
    The primary gameplay state.
    """
    
    def __init__(self, session: GameSession, config: GameConfig, player_tag: str):
        super().__init__()
        self.session = session
        self.config = config
        self.player_tag = player_tag
        
        # 1. Services
        self.net = NetworkClient(session)
        self.imgui = ImGuiService(self.window)
        self.ui_layout = GameLayout(self.net, player_tag)
        
        # 2. Map System
        # We assume map assets are in standard locations based on Config
        # In a robust system, we might reuse the MapRenderer instance from a cache, 
        # but creating a new one is fine since Atlas is pre-loaded in Session.
        
        map_path = config.get_asset_path("map/regions.png") # Fallback resolution logic needed if missing
        terrain_path = config.get_asset_path("maps/terrain.png")
        
        # Ensure we have a map path. If not found via config assets, use the one from session atlas source if possible
        if not map_path.exists() and session.atlas:
            from pathlib import Path
            map_path = Path(session.atlas.image_path)

        self.map_renderer = MapRenderer(
            map_path=map_path,
            terrain_path=terrain_path,
            cache_dir=config.cache_dir,
            preloaded_atlas=session.atlas # Important: Zero-copy reuse of heavy data
        )
        
        # 3. Camera
        center = self.map_renderer.get_center()
        self.world_camera = arcade.Camera2D()
        self.camera_controller = CameraController(center)
        
        # 4. Interaction State
        self.selected_region_id: Optional[int] = None
        self.highlight_layer = arcade.SpriteList()
        self.is_panning = False

    def on_show_view(self):
        self.window.background_color = arcade.color.BLACK
        
        # Update camera
        self.camera_controller.update_arcade_camera(self.world_camera)
        
        # Initialize Political Map
        self._refresh_political_map()

    def _refresh_political_map(self):
        """Uses the same logic as Editor to paint countries."""
        import hashlib
        state = self.net.get_state()
        
        # This duplicates logic from EditorView for now. 
        # In future, move this to a shared 'MapVisualsHelper'.
        if "regions" not in state.tables: return
        
        regions_df = state.get_table("regions")
        if "owner" not in regions_df.columns: return
        
        region_map = dict(zip(regions_df["id"], regions_df["owner"]))
        unique_owners = regions_df["owner"].unique().to_list()
        
        color_map = {}
        for tag in unique_owners:
            if not tag or tag == "None":
                color_map[tag] = (0,0,0)
                continue
            
            # Hash for color
            h = hashlib.md5(str(tag).encode()).digest()
            color_map[tag] = (h[0], h[1], h[2])
            
        self.map_renderer.update_political_layer(region_map, color_map)

    def on_resize(self, width: int, height: int):
        self.imgui.resize(width, height)
        self.world_camera.match_window()

    def on_draw(self):
        self.clear()
        
        # 1. UI Frame Start
        self.imgui.new_frame(1.0 / 60.0)
        
        # 2. World Render
        self.world_camera.use()
        
        # Use mode from layout (toggleable)
        mode = self.ui_layout.map_mode
        self.map_renderer.draw_map(mode=mode)
        
        # Selection
        self.highlight_layer.draw()
        
        # 3. UI Render
        self.window.use()
        self.ui_layout.render(self.selected_region_id, self.imgui.io.framerate)
        self.imgui.render()

    def on_update(self, delta_time: float):
        # Tick the session (Local Single Player)
        # In MP, this would be handled by the server
        self.session.tick(delta_time)

    # --- Interaction ---

    def on_mouse_press(self, x, y, button, modifiers):
        if self.imgui.on_mouse_press(x, y, button, modifiers): return
        
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._select_province(x, y)
        elif button == arcade.MOUSE_BUTTON_RIGHT:
            self.is_panning = True

    def on_mouse_release(self, x, y, button, modifiers):
        if self.imgui.on_mouse_release(x, y, button, modifiers): return
        if button == arcade.MOUSE_BUTTON_RIGHT:
            self.is_panning = False

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if self.imgui.on_mouse_drag(x, y, dx, dy, buttons, modifiers): return
        
        if self.is_panning:
            self.camera_controller.pan(dx, dy)
            self.camera_controller.update_arcade_camera(self.world_camera)

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        if self.imgui.on_mouse_scroll(x, y, scroll_x, scroll_y): return
        
        self.camera_controller.zoom_scroll(scroll_y)
        self.camera_controller.update_arcade_camera(self.world_camera)

    def on_mouse_motion(self, x, y, dx, dy):
        self.imgui.on_mouse_motion(x, y, dx, dy)

    # --- Helpers ---
    
    def _select_province(self, x, y):
        # Unproject
        world_pos = self.world_camera.unproject((x, y))
        rid = self.map_renderer.get_region_id_at_world_pos(world_pos.x, world_pos.y)
        
        self.selected_region_id = rid
        self.highlight_layer.clear()
        
        if rid is not None:
            # Highlight yellow
            s = self.map_renderer.create_highlight_sprite([rid], (255, 255, 0))
            if s: self.highlight_layer.append(s)