import arcade
from src.shared.config import GameConfig
from src.client.services.network_client_service import NetworkClient
from src.client.views.base_view import BaseImGuiView
from typing import Optional

from src.client.renderers.map_renderer import MapRenderer
from src.client.renderers.unit_renderer import UnitRenderer
from src.client.ui.components.hud.unit_context_menu import UnitContextMenu
from src.client.ui.layouts.game_layout import GameLayout
from src.client.ui.panels.unit_details_window import UnitDetailsWindow
from src.client.controllers.camera_controller import CameraController
from src.client.controllers.unit_interaction_controller import UnitInteractionController
from src.client.controllers.viewport_controller import ViewportController
from src.client.ui.core.theme import GAMETHEME


class GameView(BaseImGuiView):
    def __init__(self, session, config: GameConfig, player_tag: str, initial_pos: Optional[tuple[float, float]] = None):
        super().__init__()
        self.config = config
        self.player_tag = player_tag
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

        # 3. Initialize Renderers and HUD
        self.unit_renderer = UnitRenderer(
            camera=self.cam_ctrl,
            map_width=self.renderer.width,
            map_height=self.renderer.height,
            globe_radius=self.renderer.globe_radius,
        )
        self.unit_details_window = UnitDetailsWindow()
        self.unit_interactions = UnitInteractionController(
            unit_renderer=self.unit_renderer,
            map_renderer=self.renderer,
            net_client=self.net,
            on_unit_double_click=self.unit_details_window.open_for_unit,
        )
        self.layout = GameLayout(
            self.net,
            player_tag,
            self.viewport_ctrl,
            has_selected_units=self.unit_interactions.has_selection,
            on_move_selected_units=self._move_selected_units_from_context,
        )
        self.unit_context_menu = UnitContextMenu(
            composer=self.layout.composer,
            on_deselect=self.unit_interactions.clear_selection,
            on_view_units_list=self.unit_details_window.open_for_unit,
        )

        self.selected_region_id = None
        self._drag_start_pos = None
        self._selection_rect_start = None
        self._selection_rect_current = None
        self._right_drag_start_pos = None
        self._right_context_unit_id = None
        self._context_click_pos = None
        self._drag_threshold = 5.0

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

    def on_game_update(self, delta_time: float):
        # Feed real delta_time into ImGuiService so real_fps stays accurate.
        self.imgui.update_time(delta_time)

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

        # 4. Render Unit Overlay and UI
        self.window.use() # Switch back for UI

        visible_owners = None
        if not self.viewport_ctrl.show_all_units:
            active_country = self.viewport_ctrl.selected_country_tag or self.player_tag
            from src.client.utils.diplomacy_utils import get_military_allies, get_military_enemies
            state = self.net.get_state()
            allies = get_military_allies(state, active_country)
            enemies = get_military_enemies(state, active_country)
            visible_owners = {active_country} | allies | enemies

        self.unit_renderer.render(
            state=self.net.get_state(),
            selected_unit_id=self.unit_interactions.selected_unit_id,
            selected_unit_ids=self.unit_interactions.selected_unit_ids,
            hovered_unit_id=self.unit_interactions.hovered_unit_id,
            drag_preview=self.unit_interactions.drag_preview,
            selection_rect=self._active_selection_rect(),
            visible_owners=visible_owners,
        )
        try:
            self.layout.render(
                self.selected_region_id,
                self.imgui.real_fps,
                self.nav
            )
            self.unit_context_menu.render()
            self.unit_details_window.render(self.net.get_state())
        except Exception as e:
            print(f"[GameView] UI Rendering Error: {e}")

        self.imgui.render()

    # --- INPUT HANDLING ---

    def on_game_mouse_press(self, x, y, button, modifiers):
        if button == arcade.MOUSE_BUTTON_LEFT:
            if self.unit_interactions.on_mouse_press(x, y, button):
                self._drag_start_pos = None
                self._selection_rect_start = None
                self._selection_rect_current = None
                return
            self._drag_start_pos = (x, y)
            self._selection_rect_start = (x, y)
            self._selection_rect_current = (x, y)

        if button == arcade.MOUSE_BUTTON_RIGHT:
            if self.imgui.io.want_capture_mouse:
                return
            self._right_drag_start_pos = (x, y)
            unit = self.unit_interactions.get_unit_at(x, y)
            self._right_context_unit_id = unit.unit_id if unit else None

    def _active_selection_rect(self):
        if self._selection_rect_start is None or self._selection_rect_current is None:
            return None

        dx = self._selection_rect_current[0] - self._selection_rect_start[0]
        dy = self._selection_rect_current[1] - self._selection_rect_start[1]
        if (dx * dx + dy * dy) < self._drag_threshold * self._drag_threshold:
            return None

        return (
            self._selection_rect_start[0],
            self._selection_rect_start[1],
            self._selection_rect_current[0],
            self._selection_rect_current[1],
        )

    def _is_small_drag(self, start_pos, x: float, y: float) -> bool:
        if start_pos is None:
            return False

        dx = x - start_pos[0]
        dy = y - start_pos[1]
        return (dx * dx + dy * dy) < self._drag_threshold * self._drag_threshold

    def _open_right_click_context(self, x: float, y: float) -> None:
        self._context_click_pos = (x, y)
        if self._right_context_unit_id:
            self.unit_interactions.select_unit_by_id(self._right_context_unit_id)
            self.unit_context_menu.show(self._right_context_unit_id)
            return

        target_region_id = self.viewport_ctrl.get_region_at(x, y)
        if target_region_id:
            self.layout.show_context_menu(target_region_id)

    def _move_selected_units_from_context(self) -> None:
        if self._context_click_pos is None:
            return

        self.unit_interactions.move_selected_units_to_screen_pos(
            self._context_click_pos[0],
            self._context_click_pos[1],
        )

    def on_game_mouse_release(self, x, y, button, modifiers):
        if self.unit_interactions.on_mouse_release(x, y, button):
            self._drag_start_pos = None
            self._selection_rect_start = None
            self._selection_rect_current = None
            return

        if button == arcade.MOUSE_BUTTON_RIGHT:
            if self._is_small_drag(self._right_drag_start_pos, x, y):
                self._open_right_click_context(x, y)
            self._right_drag_start_pos = None
            self._right_context_unit_id = None
            return

        # Handle "Click" vs "Drag"
        if button == arcade.MOUSE_BUTTON_LEFT and self._drag_start_pos:
            if self._is_small_drag(self._drag_start_pos, x, y):
                self.unit_interactions.clear_selection()
                self.viewport_ctrl.on_mouse_press(self._drag_start_pos[0], self._drag_start_pos[1], button)
            else:
                self.unit_interactions.select_units_in_rect(
                    self._drag_start_pos[0],
                    self._drag_start_pos[1],
                    x,
                    y,
                )

            self._drag_start_pos = None
            self._selection_rect_start = None
            self._selection_rect_current = None

    def on_game_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if self.unit_interactions.on_mouse_drag(x, y, buttons):
            return

        if buttons & arcade.MOUSE_BUTTON_LEFT and self._selection_rect_start is not None:
            self._selection_rect_current = (x, y)
            return

        if buttons & arcade.MOUSE_BUTTON_RIGHT and self._right_drag_start_pos is None:
            return

        self.viewport_ctrl.on_mouse_drag(x, y, dx, dy, buttons)

    def on_game_mouse_motion(self, x, y, dx, dy):
        self.unit_interactions.on_mouse_motion(x, y)

    def on_game_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self.viewport_ctrl.on_mouse_scroll(x, y, scroll_x, scroll_y)

    def on_game_resize(self, width, height):
        self.world_cam.match_window()
