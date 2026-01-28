import arcade
from src.shared.config import GameConfig
from src.client.services.network_client_service import NetworkClient
from src.client.views.base_view import BaseImGuiView
from typing import Optional

from src.client.renderers.map_renderer import MapRenderer
from src.client.ui.layouts.game_layout import GameLayout
from src.client.controllers.camera_controller import CameraController
from src.client.controllers.viewport_controller import ViewportController
from src.client.utils.color_generator import generate_political_colors
from src.client.ui.theme import GAMETHEME

class GameView(BaseImGuiView):
    """
    The main gameplay view. Acts as an Orchestrator.
    
    It binds the Input Events (Arcade), Logic (Controllers), and Presentation (Layouts).
    """
    
    def __init__(self, session, config: GameConfig, player_tag: str, initial_pos: Optional[tuple[float, float]] = None):
        super().__init__()
        self.config = config
        self.net = NetworkClient(session)
        
        # Initialize Renderer with assets
        map_path = config.get_asset_path("map/regions.png")
        terrain_path = config.get_asset_path("map/terrain.png")

        self.renderer = MapRenderer(
            map_data=session.map_data,
            map_img_path=map_path,
            terrain_img_path=terrain_path
        )
        
        # Initialize Camera System
        self.world_cam = arcade.Camera2D()
        start_x, start_y = initial_pos if initial_pos else (self.renderer.width / 2, self.renderer.height / 2)
        self.cam_ctrl = CameraController((start_x, start_y))
        
        # Initialize Logic Controller
        self.viewport_ctrl = ViewportController(
            cam_ctrl=self.cam_ctrl,
            world_camera=self.world_cam,
            map_renderer=self.renderer,
            net_client=self.net,
            on_selection_change=self.on_selection_changed
        )
        
        # Initialize UI Layout
        self.layout = GameLayout(self.net, player_tag, self.viewport_ctrl)
        
        self.selected_region_id = None

    def on_show_view(self):
        self.window.background_color = GAMETHEME.col_black
        # Sync camera state immediately to prevent visual jumps on load
        self.cam_ctrl.sync_with_arcade(self.world_cam)
        self._refresh_political_map()

    def _refresh_political_map(self):
        """Fetches latest state and updates the GPU texture for the political layer."""
        state = self.net.get_state()
        if "regions" not in state.tables: return
        
        df = state.get_table("regions")
        region_map = dict(zip(df["id"], df["owner"]))
        unique_owners = df["owner"].unique().to_list()
        
        color_map = generate_political_colors(unique_owners)
        self.renderer.update_political_layer(region_map, color_map)

    def on_selection_changed(self, region_id: int | None):
        """Callback from ViewportController when selection logic changes."""
        self.selected_region_id = region_id

    def on_draw(self):
        self.clear()
        
        # 1. Start ImGui frame (must be first)
        self.imgui.new_frame()
        
        # 2. Draw Game World (Arcade Layer)
        self.world_cam.use()
        mode = "political" if self.layout.map_mode == "political" else "terrain"
        self.renderer.draw(mode=mode)
        
        # 3. Draw UI (ImGui Layer)
        self.window.use()
        
        # Calculate hover state for tooltip/highlight purposes (visual only).
        # We DO NOT use this for the Context Menu logic anymore to prevent drift issues.
        hovered_id = self.viewport_ctrl.get_region_at(self.window._mouse_x, self.window._mouse_y)

        self.layout.render(
            self.selected_region_id, 
            hovered_id, 
            self.imgui.io.framerate
        )
        
        self.imgui.render()

    # --- INPUT HANDLING ---

    def on_game_mouse_press(self, x, y, button, modifiers):
        """
        Event-driven input handling.
        
        We prioritize using these event coordinates (x, y) over polling internal states
        because they represent the exact pixel location at the moment of the click.
        """
        
        # 1. Delegate standard interactions (Pan, Zoom, Left-Click Select) to the Controller
        self.viewport_ctrl.on_mouse_press(x, y, button)

        # 2. Handle Context Menu Trigger (Right Click)
        # We explicitly calculate the region ID here and inject it into the Layout.
        # This solves the coordinate drift issue caused by render loop timing mismatches.
        if button == arcade.MOUSE_BUTTON_RIGHT:
            
            # Ask the controller to translate accurate screen coords -> World ID
            target_region_id = self.viewport_ctrl.get_region_at(x, y)
            
            if target_region_id:
                # Command the UI to open the menu for this specific ID
                self.layout.show_context_menu(target_region_id)

    def on_game_mouse_release(self, x, y, button, modifiers):
        self.viewport_ctrl.on_mouse_release(x, y, button)

    def on_game_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        self.viewport_ctrl.on_mouse_drag(x, y, dx, dy, buttons)

    def on_game_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self.viewport_ctrl.on_mouse_scroll(x, y, scroll_x, scroll_y)

    def on_game_resize(self, width, height):
        self.world_cam.match_window()