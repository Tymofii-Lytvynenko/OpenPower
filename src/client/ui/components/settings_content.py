from __future__ import annotations

from imgui_bundle import imgui, icons_fontawesome_6

from src.client.services.game_settings_service import GameSettingsService
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME


class GameSettingsContent:
    def __init__(self, settings_service: GameSettingsService, window):
        self._settings_service = settings_service
        self._window = window

    def render(self) -> None:
        self._render_display_section()
        imgui.dummy((0, 8))
        self._render_language_section()

    def _render_display_section(self) -> None:
        Prims.header("DISPLAY")

        fullscreen = self._settings_service.settings.fullscreen
        changed, fullscreen = imgui.checkbox("Fullscreen", fullscreen)
        if changed:
            self._settings_service.set_fullscreen(fullscreen, self._window)

        imgui.same_line()
        imgui.text_disabled("F11")

        current_icon = (
            icons_fontawesome_6.ICON_FA_COMPRESS
            if self._settings_service.settings.fullscreen
            else icons_fontawesome_6.ICON_FA_EXPAND
        )
        imgui.same_line()
        imgui.text_colored(GAMETHEME.colors.accent, current_icon)

    def _render_language_section(self) -> None:
        Prims.header("LOCALIZATION")

        imgui.align_text_to_frame_padding()
        imgui.text(f"{icons_fontawesome_6.ICON_FA_LANGUAGE} Language")
        imgui.same_line()
        combo_width = max(110.0, min(220.0, imgui.get_content_region_avail().x - 52.0))
        imgui.set_next_item_width(combo_width)

        options = self._settings_service.language_options
        labels = [option.label for option in options]
        selected_index = self._settings_service.selected_language_index
        changed, selected_index = imgui.combo("##Language", selected_index, labels)
        if changed:
            self._settings_service.set_language_by_index(selected_index)

        selected = self._settings_service.selected_language
        if selected.is_stub:
            imgui.same_line()
            imgui.text_disabled("STUB")
