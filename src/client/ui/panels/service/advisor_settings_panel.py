from __future__ import annotations
import polars as pl
from src.client.ui.core.panel_close_intent import PanelCloseIntent

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.components.shared.dirty_close_confirmation import (
    CloseDecision,
    DirtyCloseConfirmation,
    SaveConfirmationPreferences,
)
from src.client.ui.core.theme import GAMETHEME
from src.shared.actions import ActionUpdateAdvisorSettings
from src.shared.advisor_settings import (
    ADVISOR_DOMAINS,
    ADVISOR_STATUS_COLUMNS,
    ADVISOR_MODES,
    mode_from_preferences,
    preferences_from_modes,
)


class AdvisorSettingsPanel:
    """Edits authoritative per-country advisor modes in a source-sized draft."""

    _OPTIONS = ("manual", "automatic", "confirmations")
    _DOMAINS = ("politics", "military", "economy")

    def __init__(self, settings_service=None) -> None:
        self._close_intent = PanelCloseIntent()
        self.request_close = self._close_intent.request
        self._settings_service = settings_service
        self._draft: dict[str, bool] = {}
        self._dirty = False
        self._pending_modes: dict[str, str] | None = None
        self._pending_result_cursor = 0
        self._pending_player_id = ""
        self._pending_country = ""
        self._close_confirmation = DirtyCloseConfirmation(
            "advisor.settings.close",
            "Apply your advisor preferences before closing?",
        )
        self._local_preferences = SaveConfirmationPreferences()

    def render(self, state, context: PanelRenderContext) -> bool:
        navigation_close = self._close_intent.consume()
        player_country = self._player_country_tag(state, context)
        self._reconcile_pending(state, player_country)
        self._sync_from_state(state, player_country)
        preferences = context.save_confirmation_preferences or self._local_preferences
        close_decision = None

        with WindowManager.window(
            "Advisor settings",
            x=500,
            y=100,
            w=268,
            h=132,
            test_id="advisor.settings.panel",
            gml_template="Advisor_Settings_Window",
        ) as is_open:
            if not is_open or navigation_close:
                if not self._dirty:
                    return False
                close_decision = self._close_confirmation.request_close(
                    preferences,
                    can_apply=self._dirty and self._pending_modes is None,
                )
            else:
                imgui.begin_disabled(self._pending_modes is not None or not player_country)
                self._render_preferences()
                imgui.end_disabled()
                self._render_apply_button(state, context, player_country)

        if close_decision is not None:
            self._finish_close(close_decision, state, context, player_country)
            return False

        close_decision = self._close_confirmation.render(
            preferences,
            can_apply=self._dirty and self._pending_modes is None,
        )
        if close_decision is not None:
            self._finish_close(close_decision, state, context, player_country)
            return False
        return True

    def _render_apply_button(self, state, context: PanelRenderContext, player_country: str) -> None:
        from src.client.ui.layouts.gml_layout import suspend_gml_layout, resume_gml_layout

        # The source title frame is wider than its 268px window, placing Apply
        # outside the clipped ImGui window. Keep it in the title-side corner of
        # the content area so the GML-sized dialog remains usable.
        layout_token = suspend_gml_layout()
        try:
            window_position = imgui.get_window_pos()
            imgui.set_cursor_screen_pos((window_position.x + 240.0, window_position.y + 31.0))
            can_apply = self._dirty and self._pending_modes is None and bool(player_country)
            imgui.begin_disabled(not can_apply)
            if imgui.button("✓", (17.0, 17.0), test_id="advisor.settings.apply") and can_apply:
                self._apply(state, context, player_country)
            imgui.end_disabled()
            if imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled) and self._pending_modes is not None:
                imgui.set_tooltip("Waiting for the authoritative advisor settings update.")
        finally:
            resume_gml_layout(layout_token)

    @staticmethod
    def _player_country_tag(state, context: PanelRenderContext) -> str:
        tag = context.player_country_tag or state.globals.get("player_tag")
        if not tag and context.is_own_country:
            tag = context.target_tag
        return str(tag or "").strip().upper()

    def _sync_from_state(self, state, player_country: str) -> None:
        if self._dirty or self._pending_modes is not None:
            return
        modes = self._read_authoritative_modes(state, player_country)
        if modes is not None:
            self._draft = preferences_from_modes(modes)
            return

        self._sync_from_local_settings()

    def _sync_from_local_settings(self) -> None:
        settings = getattr(self._settings_service, "settings", None)
        self._draft = {
            f"advisor_{domain}_{option}": bool(
                getattr(settings, f"advisor_{domain}_{option}", default)
            )
            for domain in self._DOMAINS
            for option, default in (("manual", True), ("automatic", False), ("confirmations", True))
        }

    @staticmethod
    def _read_authoritative_modes(state, player_country: str) -> dict[str, str] | None:
        countries = getattr(state, "tables", {}).get("countries")
        required = {"id", *ADVISOR_STATUS_COLUMNS.values()}
        if not player_country or countries is None or not required.issubset(countries.columns):
            return None
        rows = countries.filter(
            pl.col("id").cast(pl.Utf8, strict=False).str.strip_chars().str.to_uppercase()
            == player_country
        )
        if rows.height != 1:
            return None
        modes = {
            domain: str(rows[column][0] or "").strip().lower()
            for domain, column in ADVISOR_STATUS_COLUMNS.items()
        }
        return modes if all(mode in ADVISOR_MODES for mode in modes.values()) else None

    def _reconcile_pending(self, state, player_country: str) -> None:
        if self._pending_modes is None:
            return
        results = getattr(getattr(state, "journal", None), "command_results", [])
        for result in results[self._pending_result_cursor:]:
            if str(result.get("action_type") or "") != "ActionUpdateAdvisorSettings":
                continue
            if str(result.get("player_id") or result.get("actor_id") or "") != self._pending_player_id:
                continue
            result_country = str(result.get("country_id") or "").strip().upper()
            if result_country and result_country != self._pending_country:
                continue
            status = str(result.get("status") or "").casefold()
            if status in {"rejected", "failed"}:
                self._pending_modes = None
                self._dirty = True
                return

        modes = self._read_authoritative_modes(state, player_country)
        if modes == self._pending_modes:
            self._pending_modes = None
            self._draft = preferences_from_modes(modes)
            self._dirty = False
            if self._settings_service is not None:
                self._settings_service.set_advisor_preferences(self._draft)

    def _render_preferences(self) -> None:
        layout_root = "Advisor_Settings_Window/frmInner/frmSettings"
        ui = GMLWidgets(layout_root)
        for row, option in enumerate(self._OPTIONS):
            label_component = {
                "manual": "txtManual",
                "automatic": "txtAutomatic",
                "confirmations": "txtConfirmations",
            }[option]
            imgui.text_disabled(
                option.title(),
                gml_id=f"{layout_root}/{label_component}",
            )

            for domain, component in zip(self._DOMAINS, self._domain_components(row)):
                key = f"advisor_{domain}_{option}"
                value = self._draft[key]
                changed = imgui.invisible_button(
                    f"##{key}",
                    (7.0, 7.0),
                    test_id=f"advisor.settings.{domain}.{option}",
                    gml_id=f"{layout_root}/{component}",
                )
                if changed:
                    self._draft[key] = not value
                    self._dirty = True
                    value = not value
                self._draw_toggle(value)
                if option in {"automatic", "confirmations"} and imgui.is_item_hovered():
                    imgui.set_tooltip(
                        "OpenPower evaluates a supported subset of advisor policies daily. "
                        "Automatic executes supported actions; Confirmations queues them for "
                        "review in Objectives."
                    )

        for domain, component, label in (
            ("politics", "picPoli", "P"),
            ("military", "picMili", "M"),
            ("economy", "picEcon", "E"),
        ):
            ui.text_at(
                component,
                label,
                offset=(5.0, 2.0),
                max_width=17.0,
                color=GAMETHEME.colors.text_dim,
            )

    @staticmethod
    def _draw_toggle(checked: bool) -> None:
        minimum = imgui.get_item_rect_min()
        maximum = imgui.get_item_rect_max()
        draw_list = imgui.get_window_draw_list()
        fill = GAMETHEME.colors.interaction_active if checked else GAMETHEME.colors.bg_input
        border = GAMETHEME.colors.accent if imgui.is_item_hovered() else GAMETHEME.colors.text_dim
        draw_list.add_rect_filled(minimum, maximum, imgui.get_color_u32(fill))
        draw_list.add_rect(minimum, maximum, imgui.get_color_u32(border), thickness=1.0)

    def _domain_components(self, row: int) -> tuple[str, str, str]:
        names = {
            "manual": ("togPoliManual", "togMiliManual", "togEconManual"),
            "automatic": ("togPoliAutomatic", "togMiliAutomatic", "togEconAutomatic"),
            "confirmations": (
                "togPoliConfirmations",
                "togMiliConfirmations",
                "togEconConfirmations",
            ),
        }
        return names[self._OPTIONS[row]]

    def _apply(self, state, context: PanelRenderContext, player_country: str) -> None:
        client = context.net_client
        if client is None or not player_country:
            if self._settings_service is not None:
                self._settings_service.set_advisor_preferences(self._draft)
            self._dirty = False
            return

        modes = {
            domain: mode_from_preferences(self._draft, domain)
            for domain in ADVISOR_DOMAINS
        }
        self._pending_modes = modes
        self._pending_result_cursor = len(
            getattr(getattr(state, "journal", None), "command_results", [])
        )
        self._pending_player_id = str(getattr(client, "player_id", "") or "")
        self._pending_country = player_country
        client.send_action(
            ActionUpdateAdvisorSettings(
                player_id=self._pending_player_id,
                country_tag=player_country,
                economy_status=modes["economy"],
                politics_status=modes["politics"],
                military_status=modes["military"],
            )
        )

    def _finish_close(
        self,
        decision: CloseDecision,
        state,
        context: PanelRenderContext,
        player_country: str,
    ) -> None:
        if decision is CloseDecision.APPLY:
            self._apply(state, context, player_country)
        else:
            self._dirty = False
        self._sync_from_state(state, player_country)
