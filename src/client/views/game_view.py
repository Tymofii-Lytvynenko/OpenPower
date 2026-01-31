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

        # Drag detection for selection
        self._drag_start_pos = None
        self._is_dragging = False

    def on_show_view(self):
        self.window.background_color = GAMETHEME.col_black
        self.cam_ctrl.sync_with_arcade(self.world_cam)

        # Update: Use the generic refresh
        self.viewport_ctrl.refresh_map_layer()

    def _refresh_political_map(self):
        state = self.net.get_state()
        if "regions" not in state.tables:
            return

        df = state.get_table("regions")

        # region id -> owner tag
        region_owner = dict(zip(df["id"], df["owner"]))
        unique_owners = df["owner"].unique().to_list()
        owner_colors = generate_political_colors(unique_owners)  # owner -> (r,g,b)

        # Build final map: region id -> (r,g,b)
        color_map = {}
        for rid, owner in region_owner.items():
            if owner in owner_colors:
                color_map[int(rid)] = owner_colors[owner]

        self.renderer.update_overlay(color_map)

    def on_selection_changed(self, region_id: int | None):
        """Callback from ViewportController when selection logic changes."""
        self.selected_region_id = region_id

    def on_draw(self):
        """
        Main render pass for the gameplay view.
        Coordinates the Arcade world rendering with the ImGui HUD.
        """
        # 1. Clear the screen with the theme's background color
        self.clear()

        # 2. Start the ImGui frame (Must be called before any UI logic)
        self.imgui.new_frame()

        # 3. Draw Game World (Arcade/OpenGL Layer)
        # We use the world camera to handle pan and zoom for the map
        self.window.use()
        render_mode = "political" if self.layout.map_mode == "political" else "terrain"
        self.renderer.draw(mode=render_mode)

        # 4. Draw UI (ImGui Overlay Layer)
        # Switch back to the window's coordinate system for the UI
        self.window.use()

        # Execute Layout rendering.
        # Arguments: (selected_id, hovered_id, delta_time/fps, navigation_service)
        try:
            self.layout.render(
                self.selected_region_id,
                self.imgui.io.framerate,
                self.nav
            )
        except Exception as e:
            # Basic fail-safe to prevent the whole app from crashing if a UI panel fails
            print(f"[GameView] UI Rendering Error: {e}")

        # 5. Finalize and push the ImGui draw data to the GPU
        self.imgui.render()

    # --- INPUT HANDLING ---

    def on_game_mouse_press(self, x, y, button, modifiers):
        # 1) Always handle globe interaction for potential dragging
        self.renderer.on_mouse_press(x, y, button, modifiers)

        # 2) For left clicks, store position for drag detection
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._drag_start_pos = (x, y)
            self._is_dragging = False

        # 3) Context menu (right click)
        if button == arcade.MOUSE_BUTTON_RIGHT:
            if self.layout.composer.is_background_clicked():
                target_region_id = self.viewport_ctrl.get_region_at(x, y)
                if target_region_id:
                    self.layout.show_context_menu(target_region_id)

    def on_game_mouse_release(self, x, y, button, modifiers):
        # End globe drag
        self.renderer.on_mouse_release(x, y, button, modifiers)

        # For left clicks, handle selection if it wasn't a drag
        if button == arcade.MOUSE_BUTTON_LEFT and self._drag_start_pos:
            # Check if this was a click (not a drag)
            drag_threshold = 5.0  # pixels
            dx = x - self._drag_start_pos[0]
            dy = y - self._drag_start_pos[1]
            drag_distance = (dx * dx + dy * dy) ** 0.5

            if drag_distance < drag_threshold:
                # This was a click, not a drag - handle selection
                self.viewport_ctrl.on_mouse_press(self._drag_start_pos[0], self._drag_start_pos[1], button)

            # Reset drag state
            self._drag_start_pos = None
            self._is_dragging = False

    def on_game_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        # Globe drag rotation
        if self.renderer.on_mouse_drag(x, y, dx, dy, buttons, modifiers):
            return

        # (Optional) If you later add RMB rotate or something, do it here.

    def on_game_mouse_scroll(self, x, y, scroll_x, scroll_y):
        # Globe zoom (forwarded)
        self.viewport_ctrl.on_mouse_scroll(x, y, scroll_x, scroll_y)

    def on_game_resize(self, width, height):
        self.world_cam.match_window()
