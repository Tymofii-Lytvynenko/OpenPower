from __future__ import annotations

from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.testability import semantic_region
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import active_gml_layout


_TAB_PATH = "Options_Window/frmInner/tabOptions"
_SOURCE_TABS = (
    ("profile", "PROFILE", "Tab1"),
    ("graphics", "GRAPHICS", "Tab2"),
    ("sound", "SOUND", "Tab3"),
    ("openpower", "OPENPOWER", "Tab1"),
)


class REFERENCEOptionsWindowContent:
    """Compose the source Options tabs around OpenPower's supported settings."""

    def __init__(self, settings_content, test_id_prefix: str) -> None:
        self._settings_content = settings_content
        self._test_id_prefix = test_id_prefix
        self._active_tab = 0

    def begin_session(self) -> None:
        self._forward("begin_session")

    def discard(self) -> None:
        self._forward("discard")

    def apply(self) -> bool | None:
        return self._forward("apply")

    def _forward(self, method_name: str):
        callback = getattr(self._settings_content, method_name, None)
        if callable(callback):
            return callback()

    def render(self, max_height: float | None = None) -> None:
        session = active_gml_layout()
        if session is None:
            self._settings_content.render(max_height=max_height)
            return

        tabs = GMLWidgets("Options_Window/frmInner")
        tab_layout = session.apply_tab_page_runtime_geometry(tabs.path("tabOptions"))
        tabs.frame("tabOptions")
        if tab_layout is None:
            self._settings_content.render(max_height=max_height)
            return

        self._render_tab_buttons(tabs, session)
        key, label, source_page = _SOURCE_TABS[self._active_tab]
        region_id = f"{self._test_id_prefix}.options.tab.{key}.content"
        with semantic_region(region_id, f"{label.title()} options"):
            page = GMLWidgets(_TAB_PATH)
            # Tab 2 and Tab 3 declare oversized GML page rectangles. The first
            # page supplies the actual visible viewport used by the tab control.
            page.frame("Tab1")
            if self._active_tab == 0:
                self._render_profile(page)
            elif self._active_tab == 1:
                self._render_graphics(page)
            elif self._active_tab == 2:
                self._render_sound(page)
            else:
                self._render_openpower(page, session)

    def _render_tab_buttons(self, ui: GMLWidgets, session) -> None:
        group_rect = session.rect_for(_TAB_PATH)
        for index, (key, label, _page) in enumerate(_SOURCE_TABS):
            button_rect = session.tab_button_rect(_TAB_PATH, index)
            if button_rect is None and index == len(session.layout.component(_TAB_PATH).tab_layout.tab_names):
                tab_layout = session.layout.component(_TAB_PATH).tab_layout
                button_offset = (
                    tab_layout.button_offset_left
                    + index * (tab_layout.button_width + tab_layout.button_distance),
                    0.0,
                )
                button_size = (tab_layout.button_width, tab_layout.button_height)
            elif button_rect is not None:
                button_offset = (
                    button_rect.x - group_rect.x,
                    button_rect.y - group_rect.y,
                )
                button_size = (button_rect.width, button_rect.height)
            else:
                continue

            selected = index == self._active_tab
            imgui.push_style_color(
                imgui.Col_.button,
                GAMETHEME.colors.interaction_active if selected else GAMETHEME.colors.bg_input,
            )
            try:
                clicked = ui.button_at(
                    "tabOptions",
                    label,
                    f"{self._test_id_prefix}.options.tab.{key}",
                    offset=button_offset,
                    size=button_size,
                    padding=(1.0, 0.0),
                )
            finally:
                imgui.pop_style_color()

            if clicked:
                self._active_tab = index

    @staticmethod
    def _unavailable_input(
        ui: GMLWidgets,
        slot: str,
        test_id: str,
        explanation: str,
        *,
        display_value: str = "Unavailable in OpenPower",
    ) -> None:
        imgui.begin_disabled(True)
        try:
            imgui.input_text(
                f"##{test_id}",
                display_value,
                test_id=test_id,
                gml_id=ui.path(slot),
            )
        finally:
            imgui.end_disabled()
        if imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
            imgui.set_tooltip(explanation)

    @staticmethod
    def _unavailable_combo(
        ui: GMLWidgets,
        slot: str,
        test_id: str,
        explanation: str,
    ) -> None:
        ui.combo_at(slot, f"##{test_id}", 0, ("Unavailable",), test_id, enabled=False)
        if imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
            imgui.set_tooltip(explanation)

    @staticmethod
    def _unavailable_toggle(
        ui: GMLWidgets,
        slot: str,
        test_id: str,
        explanation: str,
    ) -> None:
        ui.hitbox(slot, test_id, enabled=False, tooltip=explanation)

        rect = ui.rect(slot)
        session = active_gml_layout()
        if rect is None or session is None:
            return

        x = session.window_position[0] + rect.x - imgui.get_scroll_x()
        y = session.window_position[1] + rect.y - imgui.get_scroll_y()
        draw = imgui.get_window_draw_list()
        outline = imgui.get_color_u32(GAMETHEME.colors.text_dim)
        draw.add_rect((x, y), (x + rect.width, y + rect.height), outline)
        draw.add_line((x + 1.0, y + 1.0), (x + rect.width - 1.0, y + rect.height - 1.0), outline)

    def _render_profile(self, ui: GMLWidgets) -> None:
        root = "Tab1/"
        ui.text(root + "lblName", "Player name", test_id="options.source.profile.player_name.label")
        REFERENCEOptionsWindowContent._unavailable_input(
            ui,
            root + "edtName",
            "options.source.profile.player_name",
            "OpenPower has no player profile-name setting.",
        )

        ui.text(root + "lblAutosaveName1", "AI aggressiveness", test_id="options.source.profile.ai.label")
        meter_slot = root + "frmAIAggressivenessMtr"
        ui.meter(meter_slot, 0.0, GAMETHEME.colors.text_dim, cursor=True)
        ui.text_at(
            meter_slot,
            "N/A",
            offset=(4.0, 0.0),
            max_width=38.0,
            tooltip="OpenPower advisor modes do not provide REFERENCE's numeric AI aggressiveness value.",
            test_id="options.source.profile.ai",
        )

        settings = self._settings_content.options
        ui.text(root + "lblAutosave", "Autosave", test_id="options.source.profile.autosave.label")
        changed, enabled = ui.toggle(
            root + "togAutosave", settings.autosave_enabled, "options.source.profile.autosave",
            icon="", color=GAMETHEME.colors.accent,
        )
        if changed:
            self._settings_content.update_options(autosave_enabled=enabled)
            settings = self._settings_content.options
        if not settings.autosave_enabled:
            return
        ui.frame(root + "frmAutosave")
        ui.text(
            root + "frmAutosave/lblIncremental",
            "Incremental save",
            test_id="options.source.profile.incremental.label",
        )
        changed, incremental = ui.toggle(
            root + "frmAutosave/togIncremental", settings.autosave_incremental,
            "options.source.profile.incremental", icon="", color=GAMETHEME.colors.accent,
        )
        if changed:
            self._settings_content.update_options(autosave_incremental=incremental)
        ui.text(
            root + "frmAutosave/lblAutosaveEach",
            "Interval (minutes)",
            test_id="options.source.profile.interval.label",
        )
        changed, interval = imgui.input_int(
            "##autosave_interval", settings.autosave_interval_minutes, 0, 0,
            test_id="options.source.profile.interval",
            gml_id=ui.path(root + "frmAutosave/edtAutosaveEach"),
        )
        if changed:
            self._settings_content.update_options(autosave_interval_minutes=max(1, interval))
        ui.text(
            root + "frmAutosave/lblAutosaveName",
            "Save file name",
            test_id="options.source.profile.filename.label",
        )
        changed, name = imgui.input_text(
            "##autosave_name", settings.autosave_name, 64,
            test_id="options.source.profile.filename",
            gml_id=ui.path(root + "frmAutosave/edtAutosaveName"),
        )
        if changed:
            self._settings_content.update_options(autosave_name=name)
        validation_error = getattr(self._settings_content, "autosave_validation_error", "")
        if validation_error:
            ui.text_at(
                root + "frmAutosave",
                "Invalid save name",
                offset=(170.0, 78.0),
                max_width=200.0,
                color=GAMETHEME.colors.error,
                tooltip=validation_error,
                test_id="options.source.profile.filename.error",
                font_size=9.0,
            )

    @staticmethod
    def _render_graphics(ui: GMLWidgets) -> None:
        root = "Tab2/"
        rows = (
            ("lblResolution", "Resolution", "cboResolution"),
            ("lblQuality", "Color depth", "cboColorDepth"),
            ("lblResolution2", "Texture detail", "cboTextureDetail"),
            ("lblResolution3", "Geometric detail", "cboGeometricDetail"),
            ("lblResolution8", "Atlas detail", "cboZoomLevel"),
        )
        for label_slot, label, control_slot in rows:
            ui.text(root + label_slot, label, test_id=f"options.source.graphics.{control_slot}.label")
            REFERENCEOptionsWindowContent._unavailable_combo(
                ui,
                root + control_slot,
                f"options.source.graphics.{control_slot}",
                "OpenPower does not expose this REFERENCE renderer setting.",
            )

        toggles = (
            ("lblResolution4", "Clouds", "togClouds"),
            ("lblResolution5", "Sun", "togSun"),
            ("lblResolution6", "Moon", "togMoon"),
            ("lblResolution7", "Day cycle", "togDayCycle"),
        )
        for label_slot, label, control_slot in toggles:
            ui.text(root + label_slot, label, test_id=f"options.source.graphics.{control_slot}.label")
            REFERENCEOptionsWindowContent._unavailable_toggle(
                ui,
                root + control_slot,
                f"options.source.graphics.{control_slot}",
                "OpenPower has no matching persisted renderer visibility setting.",
            )

    @staticmethod
    def _render_sound(ui: GMLWidgets) -> None:
        unavailable_reason = (
            "OpenPower does not have separate persistent music and sound-effects channels."
        )
        for key, label, label_slot, meter_slot in (
            ("music", "Music volume", "lblMusic", "frmMusicVolume"),
            ("sound", "Sound volume", "lblSound", "frmSoundVolume"),
        ):
            ui.text(
                f"Tab3/{label_slot}",
                label,
                test_id=f"options.source.sound.{key}.label",
            )
            ui.meter(
                f"Tab3/{meter_slot}",
                0.0,
                GAMETHEME.colors.text_dim,
                cursor=True,
            )
            ui.text_at(
                f"Tab3/{meter_slot}",
                "N/A",
                offset=(4.0, 0.0),
                max_width=38.0,
                tooltip=unavailable_reason,
                test_id=f"options.source.sound.{key}",
            )

    def _render_openpower(self, ui: GMLWidgets, session) -> None:
        source_slot = "Tab1"
        rect = ui.rect(source_slot)
        if rect is None:
            self._settings_content.render()
            return

        previous_cursor = imgui.get_cursor_screen_pos()
        imgui.set_cursor_screen_pos((
            session.window_position[0] + rect.x - imgui.get_scroll_x(),
            session.window_position[1] + rect.y - imgui.get_scroll_y(),
        ))
        opened = imgui.begin_child(
            f"##{self._test_id_prefix}_openpower_options",
            (rect.width, rect.height),
            False,
            test_id=f"{self._test_id_prefix}.options.openpower.content",
        )
        try:
            if opened:
                render_content = getattr(self._settings_content, "render_content", None)
                if callable(render_content):
                    render_content()
                else:
                    self._settings_content.render(max_height=rect.height)
        finally:
            imgui.end_child()
            imgui.set_cursor_screen_pos(previous_cursor)
