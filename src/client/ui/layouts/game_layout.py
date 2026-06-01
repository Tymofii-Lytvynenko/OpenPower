from typing import Optional
import polars as pl
from imgui_bundle import imgui

from src.client.services.network_client_service import NetworkClient
from src.client.ui.components.hud.central_bar import CentralBar
from src.client.ui.components.hud.context_menu import ContextMenu
from src.client.ui.components.hud.system_bar import SystemBar
from src.client.ui.components.hud.toggle_bar import ToggleBar
from src.client.ui.components.hud.panel_manager import PanelManager
from src.client.ui.core.composer import UIComposer
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.game_panel_registry import build_game_panel_specs
from src.client.ui.panels.service.feed_presenter import FeedPresenter


class GameLayout:
    """Composition root for the Game HUD."""

    def __init__(
        self,
        net_client: NetworkClient,
        player_tag: str,
        viewport_ctrl,
        settings_service=None,
        window=None,
        has_selected_units=None,
        on_move_selected_units=None,
    ):
        self.net = net_client
        self.local_player_tag = player_tag
        self.viewport_ctrl = viewport_ctrl

        self.composer = UIComposer(GAMETHEME)
        self.panel_manager = PanelManager()
        for spec in build_game_panel_specs(self.panel_manager, settings_service, window):
            self.panel_manager.register_spec(spec)

        self.feed_presenter = FeedPresenter()
        self.central_bar = CentralBar(
            open_objectives_cb=lambda: self.panel_manager.set_visible("OBJECTIVES", True),
            open_statistics_cb=lambda: self.panel_manager.set_visible("DATA_INSPECTOR", True),
            open_mail_cb=lambda: self.panel_manager.set_visible("MAIL", True),
            open_news_cb=lambda: self.panel_manager.set_visible("NEWS_LOG", True),
        )
        self.system_bar = SystemBar(
            open_help_cb=lambda: self.panel_manager.set_visible("TOOLTIP_HELP", True),
            open_objectives_cb=lambda: self.panel_manager.set_visible("OBJECTIVES", True),
            open_console_cb=lambda: self.panel_manager.set_visible("CONSOLE", True),
            open_mail_cb=lambda: self.panel_manager.set_visible("MAIL", True),
            open_news_cb=lambda: self.panel_manager.set_visible("NEWS_LOG", True),
            open_settings_cb=lambda: self.panel_manager.set_visible("SETTINGS", True),
        )
        self.toggle_bar = ToggleBar(self.panel_manager)
        self.context_menu = ContextMenu(
            self.composer,
            self.panel_manager,
            self.viewport_ctrl,
            has_selected_units=has_selected_units,
            on_move_selected_units=on_move_selected_units,
        )

        self._last_selected_id: Optional[int] = None
        self._cached_target_tag: str = player_tag

    def render(self, selected_region_id: Optional[int], fps: float, nav_service):
        GAMETHEME.apply()
        state = self.net.get_state()

        target_tag, is_own = self._resolve_active_context(state, selected_region_id)
        hud_summary = self.feed_presenter.build_summary(state, target_tag)

        self.system_bar.render(self.net, nav_service, hud_summary)

        req_tag = self.central_bar.render(state, self.net, target_tag, is_own, hud_summary)
        if req_tag:
            self._cached_target_tag = req_tag

        self.toggle_bar.render()

        context = PanelRenderContext(
            target_tag=target_tag,
            is_own_country=is_own,
            selected_region_id=selected_region_id,
            on_focus_request=self._on_focus_region,
            net_client=self.net,
        )
        self.panel_manager.render_all(state, context)
        self.context_menu.render()

        # Render system errors warning banner if any are collected
        errors = self.net.get_system_errors()
        if errors:
            self._render_system_errors_banner(errors)

        self._render_fps(fps)

    def show_context_menu(self, region_id: int):
        self.context_menu.show(region_id)

    def _on_focus_region(self, region_id):
        self.viewport_ctrl.focus_on_region(region_id)

    def _render_fps(self, fps: float):
        imgui.set_next_window_pos((10, 10))
        flags = (
            imgui.WindowFlags_.no_decoration
            | imgui.WindowFlags_.no_inputs
            | imgui.WindowFlags_.no_background
            | imgui.WindowFlags_.always_auto_resize
        )

        if imgui.begin("##FPS", True, flags):
            imgui.text_colored((1, 1, 1, 1), f"{fps:.0f}")
        imgui.end()

    def _render_system_errors_banner(self, errors: list):
        imgui.set_next_window_pos((imgui.get_io().display_size.x * 0.5 - 250, 40))
        imgui.set_next_window_size((500, 0))
        flags = (
            imgui.WindowFlags_.no_collapse
            | imgui.WindowFlags_.always_auto_resize
        )
        imgui.push_style_color(imgui.Col_.window_bg, (0.6, 0.1, 0.1, 0.95))
        imgui.push_style_color(imgui.Col_.title_bg, (0.8, 0.1, 0.1, 1.0))
        imgui.push_style_color(imgui.Col_.title_bg_active, (0.9, 0.1, 0.1, 1.0))
        
        if imgui.begin("SIMULATION ERRORS DETECTED", True, flags):
            imgui.text_wrapped("One or more simulation systems crashed! Check console logs for full tracebacks.")
            imgui.separator()
            for err in errors[-2:]:
                imgui.text_colored((1, 1, 0, 1), f"[{err['system_id']}] {err['message']}")
            imgui.separator()
            if imgui.button("Clear errors"):
                self.net.clear_system_errors()
        imgui.end()
        
        imgui.pop_style_color(3)

    def _resolve_active_context(self, state, region_id: Optional[int]) -> tuple[str, bool]:
        if region_id != self._last_selected_id:
            self._last_selected_id = region_id
            if not region_id:
                self._cached_target_tag = self.local_player_tag
            elif "regions" in state.tables:
                try:
                    owner = state.tables["regions"].filter(pl.col("id") == region_id).item(0, "owner")
                    self._cached_target_tag = owner if owner and owner != "None" else self.local_player_tag
                except Exception:
                    self._cached_target_tag = self.local_player_tag

        return self._cached_target_tag, self._cached_target_tag == self.local_player_tag
