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


class GameLayout:
    """Composition root for the Game HUD."""

    def __init__(
        self,
        net_client: NetworkClient,
        player_tag: str,
        viewport_ctrl,
        has_selected_units=None,
        on_move_selected_units=None,
    ):
        self.net = net_client
        self.local_player_tag = player_tag
        self.viewport_ctrl = viewport_ctrl

        self.composer = UIComposer(GAMETHEME)
        self.panel_manager = PanelManager()
        for spec in build_game_panel_specs(self.panel_manager):
            self.panel_manager.register_spec(spec)

        self.central_bar = CentralBar()
        self.system_bar = SystemBar()
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

        self.system_bar.render(self.net, nav_service)

        req_tag = self.central_bar.render(state, self.net, target_tag, is_own)
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
