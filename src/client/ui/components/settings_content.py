from __future__ import annotations

from dataclasses import replace

from imgui_bundle import icons_fontawesome_6
from src.core.saves import validate_save_name
from src.client.services.display_modes import choose_best_mode, clamp_index
from src.client.services.game_settings_service import GameSettings, GameSettingsService
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME


class GameSettingsContent:
    def __init__(self, settings_service: GameSettingsService, window, *, staged: bool = False):
        self._settings_service = settings_service
        self._window = window
        self._staged = bool(staged)
        self._draft_settings = settings_service.settings if settings_service is not None else None

    def begin_session(self) -> None:
        if self._staged and self._settings_service is not None:
            self._draft_settings = self._settings_service.settings

    def discard(self) -> None:
        self.begin_session()

    def apply(self) -> bool | None:
        if not self._staged or self._settings_service is None or self._draft_settings is None:
            return
        if self.autosave_validation_error:
            return False
        self._settings_service.apply_options(self._draft_settings, self._window)
        self._sync_geo_language_runtime()
        self.begin_session()
        return True

    def _settings(self) -> GameSettings:
        if self._staged and self._draft_settings is not None:
            return self._draft_settings
        return self._settings_service.settings

    def _update_draft(self, **changes) -> None:
        if self._staged and self._draft_settings is not None:
            self._draft_settings = replace(self._draft_settings, **changes)

    def update_options(self, **changes) -> None:
        if self._staged:
            self._update_draft(**changes)
        elif self._settings_service is not None:
            self._settings_service.apply_options(replace(self._settings(), **changes), self._window)

    @property
    def options(self) -> GameSettings:
        return self._settings()

    @property
    def autosave_validation_error(self) -> str:
        settings = self._settings()
        if not self._staged or not settings.autosave_enabled:
            return ""
        try:
            validate_save_name(settings.autosave_name)
        except ValueError as error:
            return str(error)
        return ""

    def render(self, max_height: float | None = None) -> None:
        child_height = 0.0 if max_height is None else max(0.0, float(max_height))
        imgui.begin_child("SettingsScroll", (0, child_height), False)
        try:
            self.render_content()
        finally:
            imgui.end_child()

    def render_content(self) -> None:
        self._render_display_section()
        # Keep the first localization control inside the fixed-height viewport.
        imgui.dummy((0, 4))
        self._render_language_section()

    def _render_display_section(self) -> None:
        Prims.header("DISPLAY")

        settings = self._settings()
        fullscreen = settings.fullscreen
        changed, fullscreen = imgui.checkbox("Fullscreen", fullscreen)
        if changed:
            if self._staged:
                self._update_draft(fullscreen=fullscreen)
            else:
                self._settings_service.set_fullscreen(fullscreen, self._window)

        imgui.same_line()
        imgui.text_disabled("F11")

        current_icon = (
            icons_fontawesome_6.ICON_FA_COMPRESS
            if settings.fullscreen
            else icons_fontawesome_6.ICON_FA_EXPAND
        )
        imgui.same_line()
        imgui.text_colored(GAMETHEME.colors.accent, current_icon)

        reduce_motion = bool(getattr(settings, "reduce_motion", False))
        changed, reduce_motion = imgui.checkbox("Reduce motion", reduce_motion)
        if changed:
            if self._staged:
                self._update_draft(reduce_motion=reduce_motion)
            else:
                setter = getattr(self._settings_service, "set_reduce_motion", None)
                if callable(setter):
                    setter(reduce_motion)

        imgui.dummy((0, 6))
        self._render_windowed_resolution_row()
        imgui.dummy((0, 4))
        self._render_fullscreen_screen_row()
        imgui.dummy((0, 4))
        self._render_fullscreen_mode_row()

    def _render_windowed_resolution_row(self) -> None:
        settings = self._settings()
        imgui.set_next_item_width(min(220.0, imgui.get_content_region_avail().x))
        changed, values = imgui.input_int2(
            "Windowed resolution",
            [settings.windowed_width, settings.windowed_height],
        )
        if changed and len(values) == 2:
            if self._staged:
                self._update_draft(
                    windowed_width=max(800, int(values[0])),
                    windowed_height=max(600, int(values[1])),
                )
            else:
                self._settings_service.set_windowed_resolution(values[0], values[1], self._window)

    def _render_fullscreen_screen_row(self) -> None:
        screens = self._settings_service.fullscreen_screen_options()
        if not screens:
            imgui.text_disabled("Fullscreen displays are unavailable.")
            return

        screen_labels = [screen.label for screen in screens]
        if self._staged:
            selected_index = clamp_index(self._settings().fullscreen_screen_index, len(screens))
        else:
            selected_index = self._settings_service.selected_fullscreen_screen_index
        imgui.set_next_item_width(min(260.0, imgui.get_content_region_avail().x))
        changed, selected_index = imgui.combo("Fullscreen display", selected_index, screen_labels)
        if changed:
            if self._staged:
                self._update_draft(fullscreen_screen_index=selected_index)
            else:
                self._settings_service.set_fullscreen_screen_index(selected_index, self._window)

    def _render_fullscreen_mode_row(self) -> None:
        settings = self._settings()
        if self._staged:
            screen_count = len(self._settings_service.fullscreen_screen_options())
            screen_index = clamp_index(settings.fullscreen_screen_index, max(1, screen_count))
        else:
            screen_index = self._settings_service.selected_fullscreen_screen_index
        modes = self._settings_service.fullscreen_mode_options(screen_index)
        if not modes:
            imgui.text_disabled("Fullscreen modes are unavailable for the selected display.")
            return

        mode_labels = [mode.label for mode in modes]
        if self._staged:
            selected_mode = choose_best_mode(
                modes,
                settings.fullscreen_mode_width,
                settings.fullscreen_mode_height,
                settings.fullscreen_mode_rate,
            )
            selected_index = modes.index(selected_mode) if selected_mode in modes else 0
        else:
            selected_index = self._settings_service.selected_fullscreen_mode_index(screen_index)
        imgui.set_next_item_width(min(260.0, imgui.get_content_region_avail().x))
        changed, selected_index = imgui.combo("Fullscreen mode", selected_index, mode_labels)
        if changed:
            if self._staged:
                mode = modes[clamp_index(selected_index, len(modes))]
                self._update_draft(
                    fullscreen_mode_width=mode.width,
                    fullscreen_mode_height=mode.height,
                    fullscreen_mode_rate=mode.rate,
                )
            else:
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
        settings = self._settings()
        if self._staged:
            selected_index = next(
                (index for index, option in enumerate(options)
                 if option.code == settings.language_code),
                0,
            )
        else:
            selected_index = self._settings_service.selected_language_index
        changed, selected_index = imgui.combo("##Language", selected_index, labels)
        if changed:
            if self._staged:
                self._update_draft(language_code=options[clamp_index(selected_index, len(options))].code)
            else:
                self._settings_service.set_language_by_index(selected_index)

        selected = options[clamp_index(selected_index, len(options))]
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
        if self._staged:
            selected_geo_index = next(
                (index for index, option in enumerate(geo_options)
                 if option.code == settings.geo_language_code),
                0,
            )
        else:
            selected_geo_index = self._settings_service.selected_geo_language_index
        changed, selected_geo_index = imgui.combo("##GeoLanguage", selected_geo_index, geo_labels)
        if changed:
            if self._staged:
                self._update_draft(
                    geo_language_code=geo_options[
                        clamp_index(selected_geo_index, len(geo_options))
                    ].code
                )
            else:
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
