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
        imgui.begin_child("SettingsScroll", (0, 0), False)
        try:
            self._render_display_section()
            imgui.dummy((0, 8))
            self._render_language_section()
        finally:
            imgui.end_child()

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

        imgui.dummy((0, 6))
        self._render_windowed_resolution_row()
        imgui.dummy((0, 4))
        self._render_fullscreen_screen_row()
        imgui.dummy((0, 4))
        self._render_fullscreen_mode_row()

    def _render_windowed_resolution_row(self) -> None:
        settings = self._settings_service.settings
        imgui.set_next_item_width(min(220.0, imgui.get_content_region_avail().x))
        changed, values = imgui.input_int2(
            "Windowed resolution",
            [settings.windowed_width, settings.windowed_height],
        )
        if changed and len(values) == 2:
            self._settings_service.set_windowed_resolution(values[0], values[1], self._window)

    def _render_fullscreen_screen_row(self) -> None:
        screens = self._settings_service.fullscreen_screen_options()
        if not screens:
            imgui.text_disabled("Fullscreen displays are unavailable.")
            return

        screen_labels = [screen.label for screen in screens]
        selected_index = self._settings_service.selected_fullscreen_screen_index
        imgui.set_next_item_width(min(260.0, imgui.get_content_region_avail().x))
        changed, selected_index = imgui.combo("Fullscreen display", selected_index, screen_labels)
        if changed:
            self._settings_service.set_fullscreen_screen_index(selected_index, self._window)

    def _render_fullscreen_mode_row(self) -> None:
        screen_index = self._settings_service.selected_fullscreen_screen_index
        modes = self._settings_service.fullscreen_mode_options(screen_index)
        if not modes:
            imgui.text_disabled("Fullscreen modes are unavailable for the selected display.")
            return

        mode_labels = [mode.label for mode in modes]
        selected_index = self._settings_service.selected_fullscreen_mode_index(screen_index)
        imgui.set_next_item_width(min(260.0, imgui.get_content_region_avail().x))
        changed, selected_index = imgui.combo("Fullscreen mode", selected_index, mode_labels)
        if changed:
            self._settings_service.set_fullscreen_mode_by_index(selected_index, self._window)

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

        imgui.dummy((0, 4))
        imgui.align_text_to_frame_padding()
        imgui.text("Geo names")
        imgui.same_line()
        geo_combo_width = max(110.0, min(220.0, imgui.get_content_region_avail().x - 68.0))
        imgui.set_next_item_width(geo_combo_width)

        geo_options = self._settings_service.geo_language_options
        geo_labels = [option.label for option in geo_options]
        selected_geo_index = self._settings_service.selected_geo_language_index
        changed, selected_geo_index = imgui.combo("##GeoLanguage", selected_geo_index, geo_labels)
        if changed:
            self._settings_service.set_geo_language_by_index(selected_geo_index)
            self._sync_geo_language_runtime()

    def _sync_geo_language_runtime(self) -> None:
        session = getattr(self._window, "session", None)
        state = getattr(session, "state", None)
        if state is None:
            return

        globals_dict = getattr(state, "globals", None)
        if isinstance(globals_dict, dict):
            globals_dict["geo_language_code"] = self._settings_service.settings.geo_language_code
