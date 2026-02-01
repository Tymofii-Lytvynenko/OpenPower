import arcade
from src.shared.config import GameConfig
from src.client.services.network_client_service import NetworkClient
from src.client.views.base_view import BaseImGuiView
from typing import Optional

from src.client.renderers.map_renderer import MapRenderer
from src.client.ui.layouts.game_layout import GameLayout
from src.client.controllers.camera_controller import CameraController
from src.client.controllers.viewport_controller import ViewportController
from src.client.ui.theme import GAMETHEME


class GameView(BaseImGuiView):
    def __init__(self, session, config: GameConfig, player_tag: str, initial_pos: Optional[tuple[float, float]] = None):
        super().__init__()
        self.config = config
        self.net = NetworkClient(session)

        # 1. Initialize Camera System (Single Source of Truth)
        # We start with default values, initial_pos logic is moved to ViewportController if needed
        self.cam_ctrl = CameraController()
        
        # 2. Initialize Renderer (Inject Camera)
        map_path = config.get_asset_path("map/regions.png")
        terrain_path = config.get_asset_path("map/terrain.png")

        self.renderer = MapRenderer(
            camera=self.cam_ctrl,
            map_data=session.map_data,
            map_img_path=map_path,
            terrain_img_path=terrain_path
        )

        # Legacy 2D camera for UI compatibility if needed, but not used for Map anymore
        self.world_cam = arcade.Camera2D()

        # 3. Initialize Logic Controller
        self.viewport_ctrl = ViewportController(
            cam_ctrl=self.cam_ctrl,
            world_camera=self.world_cam,
            map_renderer=self.renderer,
            net_client=self.net,
            on_selection_change=self.on_selection_changed
        )

        # 4. Initialize UI Layout
        self.layout = GameLayout(self.net, player_tag, self.viewport_ctrl)

        self.selected_region_id = None
        self._drag_start_pos = None

    def on_show_view(self):
        self.window.background_color = GAMETHEME.col_black
        self.viewport_ctrl.refresh_map_layer()

    def on_selection_changed(self, region_id: int | None):
        self.selected_region_id = region_id

    def on_draw(self):
        self.clear()
        self.imgui.new_frame()

        # Draw 3D World
        self.window.use()
        is_political = (self.layout.map_mode == "political")
        self.renderer.set_overlay_style(enabled=is_political, opacity=0.90)
        self.renderer.draw()

        # Draw UI
        self.window.use()
        try:
            self.layout.render(
                self.selected_region_id,
                self.imgui.io.framerate,
                self.nav
            )
        except Exception as e:
            print(f"[GameView] UI Rendering Error: {e}")

        self.imgui.render()

    # --- INPUT HANDLING ---

    def on_game_mouse_press(self, x, y, button, modifiers):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._drag_start_pos = (x, y)

        if button == arcade.MOUSE_BUTTON_RIGHT:
            if self.layout.composer.is_background_clicked():
                target_region_id = self.viewport_ctrl.get_region_at(x, y)
                if target_region_id:
                    self.layout.show_context_menu(target_region_id)

    def on_game_mouse_release(self, x, y, button, modifiers):
        # For left clicks, handle selection if it wasn't a drag
        if button == arcade.MOUSE_BUTTON_LEFT and self._drag_start_pos:
            drag_threshold = 5.0
            dx = x - self._drag_start_pos[0]
            dy = y - self._drag_start_pos[1]
            drag_distance = (dx * dx + dy * dy) ** 0.5

            if drag_distance < drag_threshold:
                # It was a Click
                self.viewport_ctrl.on_mouse_press(self._drag_start_pos[0], self._drag_start_pos[1], button)
            
            self._drag_start_pos = None

    def on_game_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        # Forward drag to controller (which handles rotation)
        self.viewport_ctrl.on_mouse_drag(x, y, dx, dy, buttons)

    def on_game_mouse_scroll(self, x, y, scroll_x, scroll_y):
        # Forward scroll to controller (which handles zoom)
        self.viewport_ctrl.on_mouse_scroll(x, y, scroll_x, scroll_y)

    def on_game_resize(self, width, height):
        self.world_cam.match_window()