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

        # 1. Initialize Camera & Renderer
        # We reuse the shared renderer from the Window to keep the state (position/zoom) intact.
        if self.window.shared_renderer:
            self.renderer = self.window.shared_renderer
            self.cam_ctrl = self.renderer.camera
            
            # CRITICAL: We DO NOT reset distance or pitch here. 
            # We let it persist from the previous screen (Loading/NewGameView).
            
            # Ensure political overlay is ON for gameplay
            self.renderer.set_overlay_style(enabled=True, opacity=0.90)
        else:
            # Fallback if accessed directly without main menu (Debug scenarios)
            self.cam_ctrl = CameraController()
            map_path = config.get_asset_path("map/regions.png")
            terrain_path = config.get_asset_path("map/terrain.png")
            
            self.renderer = MapRenderer(
                camera=self.cam_ctrl,
                map_data=session.map_data,
                map_img_path=map_path,
                terrain_img_path=terrain_path
            )

        # Legacy 2D camera (kept for safety, though unused by 3D globe)
        self.world_cam = arcade.Camera2D()

        # 2. Initialize Logic Controller
        self.viewport_ctrl = ViewportController(
            cam_ctrl=self.cam_ctrl,
            world_camera=self.world_cam,
            map_renderer=self.renderer,
            net_client=self.net,
            on_selection_change=self.on_selection_changed
        )

        # 3. Initialize UI Layout
        self.layout = GameLayout(self.net, player_tag, self.viewport_ctrl)

        self.selected_region_id = None
        self._drag_start_pos = None

        # 4. Handle Initial Focusing
        # If initial_pos is passed (e.g. centroid of selected country), make sure we look at it.
        # Since 'look_at_pixel_coords' only changes rotation (yaw/pitch) and preserves distance,
        # the zoom level will stay consistent with what the user set in the menu.
        if initial_pos:
            # Convert World Coords (Bottom-Left Origin) -> Pixel Coords (Top-Left Origin)
            world_x, world_y = initial_pos
            map_h = session.map_data.height
            px = world_x
            py = map_h - world_y 
            
            self.cam_ctrl.look_at_pixel_coords(
                px, py, 
                self.renderer.width, 
                self.renderer.height
            )

    def on_show_view(self):
        self.window.background_color = (10, 10, 10, 255)
        self.viewport_ctrl.refresh_map_layer()

    def on_selection_changed(self, region_id: int | None):
        self.selected_region_id = region_id

    def on_draw(self):
        # 1. Clear Screen
        self.clear()
        
        # 2. ImGui Start
        self.imgui.new_frame()
        # Note: Layout setup happens inside layout.render()

        # 3. Render 3D World
        # CRITICAL FIX: Reset OpenGL Context before drawing 3D
        ctx = self.window.ctx
        ctx.scissor = None
        ctx.viewport = (0, 0, self.window.width, self.window.height)
        ctx.enable_only((ctx.DEPTH_TEST, ctx.BLEND))

        self.renderer.draw()

        # 4. Render UI
        self.window.use() # Switch back for UI
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
        # Handle "Click" vs "Drag"
        if button == arcade.MOUSE_BUTTON_LEFT and self._drag_start_pos:
            drag_threshold = 5.0
            dx = x - self._drag_start_pos[0]
            dy = y - self._drag_start_pos[1]
            drag_distance = (dx * dx + dy * dy) ** 0.5

            if drag_distance < drag_threshold:
                # It was a click
                self.viewport_ctrl.on_mouse_press(self._drag_start_pos[0], self._drag_start_pos[1], button)
            
            self._drag_start_pos = None

    def on_game_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        self.viewport_ctrl.on_mouse_drag(x, y, dx, dy, buttons)

    def on_game_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self.viewport_ctrl.on_mouse_scroll(x, y, scroll_x, scroll_y)

    def on_game_resize(self, width, height):
        self.world_cam.match_window()