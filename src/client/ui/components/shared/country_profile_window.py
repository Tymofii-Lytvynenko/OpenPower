from __future__ import annotations

from collections.abc import Callable, Mapping

from imgui_bundle import icons_fontawesome_6

from src.client.services.country_profile import (
    PROFILE_METRICS,
    CountryProfileCandidate,
    suggest_country_profiles,
)
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.shared.panel_data import resolve_country_name


_GML_METRIC_SLOTS = {
    "economic": "Economic",
    "political": "Politic",
    "military": "Military",
}
_PROFILE_ICONS = {
    "political": ("picPolitic", icons_fontawesome_6.ICON_FA_BUILDING_COLUMNS, "politics"),
    "military": ("picPolitic1", icons_fontawesome_6.ICON_FA_PERSON_MILITARY_RIFLE, "military"),
    "economic": ("picPolitic2", icons_fontawesome_6.ICON_FA_SACK_DOLLAR, "economy"),
}


class CountryProfileWindow:
    """Source-sized country recommender backed by the current OpenPower country table."""

    def __init__(self, on_confirm: Callable[[str], None]):
        self._on_confirm = on_confirm
        self._open = False
        self._country_rows: list[Mapping[str, object]] = []
        self._desired_values = {metric: 0.5 for metric in PROFILE_METRICS}
        self._enabled_metrics = {metric: True for metric in PROFILE_METRICS}
        self._selected_country_id: str | None = None
        self._ranking_dirty = True
        self._candidates: list[CountryProfileCandidate] = []

    @property
    def is_open(self) -> bool:
        return self._open

    def show(self, state, eligible_country_ids: list[str]) -> None:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            self._country_rows = []
        else:
            eligible = {str(tag).strip().upper() for tag in eligible_country_ids}
            rows = countries.to_dicts()
            self._country_rows = [
                {
                    **row,
                    "id": str(row.get("id") or "").strip().upper(),
                    "name": resolve_country_name(state, str(row.get("id") or "").strip().upper()),
                }
                for row in rows
                if str(row.get("id") or "").strip().upper() in eligible
            ]
        self._selected_country_id = None
        self._ranking_dirty = True
        self._open = True

    def close(self) -> None:
        self._open = False
        self._selected_country_id = None

    def render(self, screen_width: float, screen_height: float) -> None:
        if not self._open:
            return

        x = (float(screen_width) - 271.0) / 2.0
        y = (float(screen_height) - 359.0) / 2.0
        window_open = True
        with WindowManager.window(
            "Country Profile",
            x=x,
            y=y,
            w=271,
            h=359,
            test_id="new_game.country_profile.dialog",
            follow_position=True,
        ) as window_open:
            if window_open:
                self._render_content()
        if not window_open:
            self.close()

    def _render_content(self) -> None:
        ui = GMLWidgets("Country_Profile_Window/frmInner")
        ui.text("frmDesired/lblTitle", "DESIRED PROFILE")
        enabled_changed = False
        value_changed = False

        for metric, profile_metric in PROFILE_METRICS.items():
            label = profile_metric.label
            slot = _GML_METRIC_SLOTS[metric]
            toggle_path = f"frmDesired/tog{slot}"
            slider_path = f"frmDesired/frm{slot}"
            changed, enabled = imgui.checkbox(
                f"##profile-{metric}",
                self._enabled_metrics[metric],
                test_id=f"new_game.profile.filter.{metric}",
                gml_id=ui.path(toggle_path),
            )
            if changed:
                self._enabled_metrics[metric] = bool(enabled)
                enabled_changed = True
            if imgui.is_item_hovered():
                imgui.set_tooltip(label)

            changed, value = ui.meter_slider(
                slider_path,
                self._desired_values[metric],
                f"new_game.profile.desired.{metric}",
                GAMETHEME.colors.positive,
                tooltip=label,
                show_cursor=False,
            )
            if changed:
                self._desired_values[metric] = float(value)
                value_changed = True
            if imgui.is_item_hovered():
                imgui.set_tooltip(label)

        if enabled_changed or value_changed:
            self._selected_country_id = None

        ui.text("frmDesired/lblGoals", "MATCH")
        ui.text("frmSuggested/lblTitle", "SUGGESTED COUNTRIES")
        if enabled_changed or value_changed:
            self._ranking_dirty = True
        if self._ranking_dirty:
            self._candidates = suggest_country_profiles(
                self._country_rows,
                self._desired_values,
                self._enabled_metrics,
            )
            self._ranking_dirty = False
        candidates = self._candidates
        selected = next(
            (candidate for candidate in candidates if candidate.country_id == self._selected_country_id),
            None,
        )
        self._render_country_list(ui, candidates)
        ui.rule("frmSuggested/picSep")
        ui.text("frmSuggested/lblGoals2", "SELECTED COUNTRY RANKS")
        self._render_suggestion_ranks(ui, selected, len(self._country_rows))

        ui.text(
            "frmSuggested/lblRank",
            f"{selected.country_id}" if selected else "",
            color=GAMETHEME.colors.accent,
            test_id="new_game.profile.selected_tag",
        )
        if ui.button(
            "btnConfirm",
            "SELECT",
            "new_game.profile.confirm",
            enabled=selected is not None,
            dynamic_enabled=True,
        ):
            self._on_confirm(selected.country_id)
            self.close()
        if ui.button("btnCancel", "CANCEL", "new_game.profile.cancel"):
            self.close()

    def _render_suggestion_ranks(
        self,
        ui: GMLWidgets,
        selected: CountryProfileCandidate | None,
        country_count: int,
    ) -> None:
        for metric in PROFILE_METRICS:
            path = f"frmSuggested/frm{_GML_METRIC_SLOTS[metric]}"
            rank = selected.rank_for(metric) if selected else 0
            fraction = (country_count + 1 - rank) / country_count if country_count and rank else 0.0
            icon_slot, icon, color_name = _PROFILE_ICONS[metric]
            color = getattr(GAMETHEME.colors, color_name)
            ui.text_at(
                f"frmSuggested/{icon_slot}",
                icon,
                offset=(1.0, 1.0),
                color=color,
                max_width=40.0,
                tooltip=PROFILE_METRICS[metric].label,
                font_size=12.0,
                test_id=f"new_game.profile.rank_icon.{metric}",
            )
            ui.meter(path, fraction, GAMETHEME.colors.positive)

    def _render_country_list(
        self,
        ui: GMLWidgets,
        candidates: list[CountryProfileCandidate],
    ) -> None:
        list_path = ui.path("frmSuggested/lstCountries")
        child_open = imgui.begin_child(
            "CountryProfileSuggestions",
            (216.0, 76.0),
            False,
            test_id="new_game.profile.candidate_list",
            gml_id=list_path,
        )
        if child_open:
            for candidate in candidates:
                label = f"{candidate.name} ({candidate.country_id})"
                if imgui.selectable(
                    label,
                    self._selected_country_id == candidate.country_id,
                    test_id=f"new_game.profile.candidate.{candidate.country_id}",
                )[0]:
                    self._selected_country_id = candidate.country_id
            if not candidates:
                imgui.text_disabled("No eligible countries.")
        imgui.end_child()
