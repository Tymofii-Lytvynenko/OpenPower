from contextlib import nullcontext
from time import perf_counter_ns
import arcade
from src.shared.config import GameConfig
from src.client.services.network_client_service import NetworkClient
from src.client.views.base_view import BaseImGuiView
from typing import Optional

from src.client.renderers.map_renderer import MapRenderer
from src.client.renderers.unit_renderer import UnitRenderer
from src.client.renderers.event_renderer import EventRenderer
from src.client.renderers.battle_effect_renderer import BattleEffectRenderer
from src.client.ui.components.hud.unit_context_menu import UnitContextMenu
from src.client.ui.components.hud.unit_order_targeting_prompt import UnitOrderTargetingPrompt
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.layouts.game_layout import GameLayout
from src.client.ui.panels.unit_details_window import UnitDetailsWindow
from src.client.ui.panels.military.map_information_windows import MapInformationWindows
from src.client.controllers.camera_controller import CameraController
from src.client.controllers.unit_interaction_controller import UnitInteractionController
from src.client.controllers.viewport_controller import ViewportController
from src.shared.actions import ActionDispatchUnitDeployment


class GameView(BaseImGuiView):
    def __init__(self, session, config: GameConfig, player_tag: str, initial_pos: Optional[tuple[float, float]] = None):
        super().__init__()
        self.config = config
        self.player_tag = player_tag
        self.net = NetworkClient(session)
        self._performance = getattr(getattr(session, "telemetry", None), "collector", None)
        self._last_frame_ns = None

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
        self.event_renderer = EventRenderer(
            camera=self.cam_ctrl,
            map_width=self.renderer.width,
            map_height=self.renderer.height,
            globe_radius=self.renderer.globe_radius,
        )
        self.battle_effect_renderer = BattleEffectRenderer(
            camera=self.cam_ctrl,
            map_width=self.renderer.width,
            map_height=self.renderer.height,
            globe_radius=self.renderer.globe_radius,
        )
        self.unit_details_window = UnitDetailsWindow()
        self.map_information = MapInformationWindows(player_tag)
        self._deployment_drag_unit_ids: tuple[str, ...] = ()
        self._deployment_drop_over_ui = False
        self.unit_interactions = UnitInteractionController(
            unit_renderer=self.unit_renderer,
            map_renderer=self.renderer,
            net_client=self.net,
            on_unit_double_click=self.unit_details_window.open_for_unit,
            on_move_requested=lambda *args: self.layout.unit_move_orders.request(*args),
            can_box_select_unit=lambda unit: unit.owner.upper() == player_tag.upper(),
        )
        self.layout = GameLayout(
            self.net,
            player_tag,
            self.viewport_ctrl,
            settings_service=getattr(self.window, "settings", None),
            window=self.window,
            has_selected_units=self.unit_interactions.has_selection,
            on_move_selected_units=self._move_selected_units_from_context,
            on_deployment_drag_start=self._start_deployment_drag,
        )
        self.unit_context_menu = UnitContextMenu(
            composer=self.layout.composer,
            on_deselect=self.unit_interactions.clear_selection,
            on_view_units_list=self.layout.unit_reorganization.open_unit_list,
            on_set_readiness=self._set_unit_readiness,
            on_split=self.layout.unit_reorganization.open_split,
            on_merge=self.layout.unit_reorganization.open_merge,
            on_move_requested=self._begin_context_move_targeting,
            on_attack_requested=self._begin_context_attack_targeting,
        )
        self.unit_order_targeting_prompt = UnitOrderTargetingPrompt()

        self.selected_region_id = None
        self._drag_start_pos = None
        self._selection_rect_start = None
        self._selection_rect_current = None
        self._right_drag_start_pos = None
        self._right_context_unit_id = None
        self._context_click_pos = None
        self._drag_threshold = 5.0
        self._visible_owners_cache_key: tuple | None = None
        self._visible_owners_cache: set[str] | None = None

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

    def _set_unit_readiness(self, unit_id: str, target_status: str) -> None:
        self.unit_interactions.selected_unit_ids = {unit_id}
        self.unit_interactions.set_selected_units_readiness(target_status)

    def _start_deployment_drag(self, unit_ids: str | list[str]) -> None:
        values = [unit_ids] if isinstance(unit_ids, str) else unit_ids
        self._deployment_drag_unit_ids = tuple(dict.fromkeys(
            str(unit_id or "").strip() for unit_id in values if str(unit_id or "").strip()
        ))

    def on_mouse_release(self, x, y, button, modifiers):
        if button != arcade.MOUSE_BUTTON_LEFT or not self._deployment_drag_unit_ids:
            return super().on_mouse_release(x, y, button, modifiers)

        unit_ids = self._deployment_drag_unit_ids
        self._deployment_drag_unit_ids = ()
        self.imgui.on_mouse_release(x, y, button, modifiers)
        if self._deployment_drop_over_ui:
            return

        region_id = self.renderer.get_region_id_at_screen_pos(x, y)
        if region_id <= 0:
            return
        for unit_id in unit_ids:
            self.net.send_action(ActionDispatchUnitDeployment(
                player_id=self.net.player_id,
                unit_id=unit_id,
                destination_region_id=int(region_id),
            ))

    def on_game_update(self, delta_time: float):
        # Feed real delta_time into ImGuiService so real_fps stays accurate.
        self.imgui.update_time(delta_time)
        self.layout.dispatch_pending_navigation(self.nav)

    def on_selection_changed(self, region_id: int | None):
        self.selected_region_id = region_id

    def _measure_performance(self, name):
        collector = getattr(self, "_performance", None)
        return collector.measure(name) if collector is not None and collector.enabled else nullcontext()

    def on_draw(self):
        collector = getattr(self, "_performance", None)
        if collector is not None and collector.enabled:
            now = perf_counter_ns()
            if self._last_frame_ns is not None:
                interval = (now - self._last_frame_ns) / 1_000_000
                collector.observe("render.frame_interval_ms", interval)
                if interval > 0:
                    collector.gauge("render.fps", 1000 / interval, "fps")
            self._last_frame_ns = now
            with collector.measure("render.frame_cpu_ms"):
                self._draw_game()
        else:
            self._last_frame_ns = None
            self._draw_game()

    def _draw_game(self):
        # ImGui and batched overlays can leave a clipping rectangle active. It must be
        # removed before clearing, otherwise stale depth values cut holes into the globe.
        ctx = self.window.ctx
        ctx.scissor = None
        # Arcade's window framebuffer converts this logical viewport to pixels.
        ctx.viewport = (0, 0, *self.window.get_size())
        ctx.enable_only(ctx.DEPTH_TEST, ctx.BLEND)

        # 1. Clear Screen
        self.clear()
        
        # 2. ImGui Start
        self.imgui.new_frame()
        # Note: Layout setup happens inside layout.render()

        state = self.net.get_state()
        self.viewport_ctrl.refresh_map_layer_if_stale(state)

        # 3. Render 3D World

        with self._measure_performance("render.map_ms"):
            self.renderer.draw()

        # 4. Render Unit Overlay and UI
        self.window.use() # Switch back for UI
        presentation_total_minutes = self.net.get_display_total_minutes()

        visible_owners = None
        if state is not None and not self.viewport_ctrl.show_all_units:
            active_country = self.viewport_ctrl.selected_country_tag or self.player_tag
            visible_owners = self._visible_unit_owners(state, active_country)

        with self._measure_performance("render.units_ms"):
            self.unit_renderer.render(
                state=state,
                selected_unit_id=self.unit_interactions.selected_unit_id,
                selected_unit_ids=self.unit_interactions.selected_unit_ids,
                hovered_unit_id=self.unit_interactions.hovered_unit_id,
                drag_preview=self.unit_interactions.drag_preview,
                selection_rect=self._active_selection_rect(),
                visible_owners=visible_owners,
                show_engagement_zones=self.viewport_ctrl.show_engagement_zones,
                presentation_total_minutes=presentation_total_minutes,
                viewer_country_tag=self.viewport_ctrl.selected_country_tag or self.player_tag,
            )

        # Draw random event placards above affected regions
        with self._measure_performance("render.effects_ms"):
            self.event_renderer.render(state)

            settings_service = getattr(self.window, "settings", None)
            reduce_motion = bool(
                getattr(getattr(settings_service, "settings", None), "reduce_motion", False)
            )
            self.battle_effect_renderer.render(
                state,
                presentation_total_minutes,
                reduce_motion=reduce_motion,
            )

        with self._measure_performance("render.ui_ms"):
            try:
                self.layout.render(
                    self.selected_region_id,
                    self.imgui.real_fps,
                    self.nav,
                    state=state,
                    presentation_total_minutes=presentation_total_minutes,
                )
                self.unit_context_menu.render()
                self.unit_order_targeting_prompt.render(
                    self.unit_interactions.pending_order_mode,
                    self.unit_interactions.cancel_order_targeting,
                )
                self.unit_details_window.render(state)
                self._render_map_information(state)
            except Exception as e:
                print(f"[GameView] UI Rendering Error: {e}")

        self._deployment_drop_over_ui = imgui.is_window_hovered(imgui.HoveredFlags_.any_window)
        with self._measure_performance("render.imgui_ms"):
            self.imgui.render()

    def _render_map_information(self, state):
        self.map_information.render_selected_unit(
            state, self.unit_interactions.selected_unit_ids, self.unit_renderer.get_unit,
            self.window.height, dragging=self.unit_interactions.drag_preview is not None,
        )
        mouse = imgui.get_mouse_pos()
        control_active = (imgui.is_key_down(imgui.Key.tab) and not imgui.get_io().want_capture_mouse
                          and not imgui.get_io().want_text_input)
        region_id = self.viewport_ctrl.get_region_at(mouse.x, self.window.height - mouse.y) if control_active else None
        self.map_information.render_region(state, region_id, (mouse.x, mouse.y), active=control_active)

    def _visible_unit_owners(self, state, active_country: str) -> set[str]:
        revisions = getattr(state, "table_revisions", {})
        cache_key = (
            active_country,
            int(revisions.get("countries_treaties", 0)),
            int(revisions.get("countries_wars", 0)),
        )
        if cache_key == self._visible_owners_cache_key and self._visible_owners_cache is not None:
            return self._visible_owners_cache

        from src.client.utils.diplomacy_utils import get_military_allies, get_military_enemies

        visible = (
            {active_country}
            | get_military_allies(state, active_country)
            | get_military_enemies(state, active_country)
        )
        self._visible_owners_cache_key = cache_key
        self._visible_owners_cache = visible
        return visible

    # --- INPUT HANDLING ---

    def _begin_context_move_targeting(self, unit_id: str) -> None:
        if self._prepare_owned_context_selection(unit_id):
            self.unit_interactions.begin_move_order_targeting()
            self._clear_map_selection_gesture()

    def _begin_context_attack_targeting(self, unit_id: str) -> None:
        if self._prepare_owned_context_selection(unit_id):
            self.unit_interactions.begin_attack_move_targeting()
            self._clear_map_selection_gesture()

    def _prepare_owned_context_selection(self, unit_id: str) -> bool:
        if not self.unit_interactions.focus_context_unit(unit_id):
            return False
        owned_ids = {
            selected_id
            for selected_id in self.unit_interactions.selected_unit_ids
            if (unit := self.unit_interactions.get_unit_by_id(selected_id)) is not None
            and unit.owner.upper() == self.player_tag.upper()
        }
        if unit_id not in owned_ids:
            return False
        self.unit_interactions.selected_unit_ids = owned_ids
        if self.unit_interactions.selected_unit_id not in owned_ids:
            self.unit_interactions.selected_unit_id = unit_id
        return True

    def _has_owned_context_selection(self) -> bool:
        return any(
            (unit := self.unit_interactions.get_unit_by_id(unit_id)) is not None
            and unit.owner.upper() == self.player_tag.upper()
            for unit_id in self.unit_interactions.selected_unit_ids
        )

    def _clear_map_selection_gesture(self) -> None:
        self._drag_start_pos = None
        self._selection_rect_start = None
        self._selection_rect_current = None
        self._right_drag_start_pos = None
        self._right_context_unit_id = None

    def on_game_mouse_press(self, x, y, button, modifiers):
        if button == arcade.MOUSE_BUTTON_LEFT:
            if self.unit_interactions.pending_order_mode is not None:
                if self.imgui.io.want_capture_mouse:
                    return
                self.unit_interactions.resolve_order_target_click(x, y)
                self._clear_map_selection_gesture()
                return
            if self.unit_interactions.on_mouse_press(x, y, button, modifiers):
                self._drag_start_pos = None
                self._selection_rect_start = None
                self._selection_rect_current = None
                return
            self._drag_start_pos = (x, y)
            self._selection_rect_start = (x, y)
            self._selection_rect_current = (x, y)

        if button == arcade.MOUSE_BUTTON_RIGHT:
            if self.unit_interactions.cancel_order_targeting():
                self._clear_map_selection_gesture()
                return
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
            if self.unit_interactions.attack_selected_units(self._right_context_unit_id):
                return
            self.unit_interactions.focus_context_unit(self._right_context_unit_id)
            self.unit_context_menu.show(
                self._right_context_unit_id,
                orders_enabled=self._has_owned_context_selection(),
            )
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
        if self.unit_interactions.on_mouse_release(x, y, button, modifiers):
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
                if not self.layout.select_battle_at(self.battle_effect_renderer, x, y, self.window.height):
                    self.viewport_ctrl.on_mouse_press(self._drag_start_pos[0], self._drag_start_pos[1], button)
            else:
                self.unit_interactions.select_units_in_rect(
                    self._drag_start_pos[0],
                    self._drag_start_pos[1],
                    x,
                    y,
                    modifiers,
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

    def on_game_key_press(self, symbol, modifiers):
        if symbol == arcade.key.ESCAPE:
            self.unit_interactions.cancel_order_targeting()

    def on_game_resize(self, width, height):
        self.world_cam.match_window()
