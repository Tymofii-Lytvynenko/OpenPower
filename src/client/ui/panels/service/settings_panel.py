from __future__ import annotations

from imgui_bundle import imgui

from src.client.services.game_settings_service import GameSettingsService
from src.client.ui.components.settings_content import GameSettingsContent
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext


class SettingsPanel:
    def __init__(self, settings_service: GameSettingsService | None, window):
        self._content = (
            GameSettingsContent(settings_service, window)
            if settings_service is not None and window is not None
            else None
        )

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("SETTINGS", x=800, y=90, w=460, h=480) as is_open:
            if not is_open:
                return False
            if self._content is None:
                imgui.text_disabled("Settings unavailable.")
            else:
                self._content.render()
            return True
