from __future__ import annotations

from collections.abc import Callable, Sequence

from src.client.services.campaign_selection import CampaignScenarioPreview
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.theme import GAMETHEME


class SinglePlayerSetupWindow:
    """Render country and party setup in the source 346x341 REFERENCE window."""

    _ROOT = "Start_Single_Player"
    _GOAL_ROWS = tuple(
        (index, f"frmInner/frmGoals/frmTog{index}",
         f"frmInner/frmGoals/txtGoal{index}",
         f"frmInner/frmGoals/cboGoal{index}")
        for index in range(1, 6)
    )

    def render(
        self,
        screen_width: float,
        screen_height: float,
        country_options: Sequence[tuple[str, str]],
        selected_country_id: str | None,
        selected_party_name: str,
        party_available: bool,
        scenario_preview: CampaignScenarioPreview,
        on_select_country: Callable[[str], None],
        on_open_profile: Callable[[], None],
        on_open_party: Callable[[], None],
        on_start: Callable[[], None],
        on_back: Callable[[], None],
    ) -> None:
        window_open = True
        with WindowManager.window(
            "START SINGLE PLAYER",
            x=(float(screen_width) - 346.0) / 2.0,
            y=(float(screen_height) - 341.0) / 2.0,
            w=346,
            h=341,
            test_id="new_game.panel",
            gml_template=self._ROOT,
            follow_position=True,
        ) as window_open:
            if window_open:
                self._render_content(
                    country_options,
                    selected_country_id,
                    selected_party_name,
                    party_available,
                    scenario_preview,
                    on_select_country,
                    on_open_profile,
                    on_open_party,
                    on_start,
                )
        if not window_open:
            on_back()

    def _render_content(
        self,
        country_options: Sequence[tuple[str, str]],
        selected_country_id: str | None,
        selected_party_name: str,
        party_available: bool,
        scenario_preview: CampaignScenarioPreview,
        on_select_country: Callable[[str], None],
        on_open_profile: Callable[[], None],
        on_open_party: Callable[[], None],
        on_start: Callable[[], None],
    ) -> None:
        ui = GMLWidgets(self._ROOT)
        self._draw_source_frames(ui)

        selected_country = next(
            (
                country_id for country_id, _ in country_options
                if country_id == str(selected_country_id or "").upper()
            ),
            "",
        )
        ui.text_at(
            "frmInner/frmCountrySelection/lblTitle",
            f"COUNTRY: {selected_country or 'CHOOSE'}",
            test_id="new_game.selected_country",
        )
        labels = ["Select country", *(label for _, label in country_options)]
        current_index = next(
            (
                index + 1 for index, (country_id, _) in enumerate(country_options)
                if country_id == str(selected_country_id or "").upper()
            ),
            0,
        )
        changed, selected_index = ui.combo_at(
            "frmInner/frmCountrySelection/cboCountry",
            "##new-game-country",
            current_index,
            labels,
            "new_game.country.select",
            enabled=bool(country_options),
        )
        if changed and selected_index > 0:
            on_select_country(country_options[selected_index - 1][0])
        elif changed:
            on_select_country("")

        if ui.button(
            "frmInner/frmCountrySelection/btnProfile",
            "PROFILE",
            "new_game.profile.open",
            enabled=bool(country_options),
            tooltip="Suggest a country from the current scenario's eligible countries.",
        ):
            on_open_profile()

        self._render_sphere_summary(ui, scenario_preview, bool(selected_country_id))
        ui.text_at("frmInner/frmSphereControl/lblParty", "PARTY")
        ui.text_at(
            "frmInner/frmSphereControl/txtParty",
            selected_party_name or "Select a country first",
            max_width=230.0,
            color=GAMETHEME.colors.text_main if selected_party_name else GAMETHEME.colors.text_dim,
            test_id="new_game.selected_party",
        )
        if ui.button(
            "frmInner/frmSphereControl/btnParty",
            "SELECT PARTY",
            "new_game.party_selection.open",
            enabled=bool(selected_country_id and party_available),
            dynamic_enabled=True,
            tooltip="Choose the OpenPower political party that represents the player.",
        ):
            on_open_party()

        self._render_objectives(ui, scenario_preview)
        if ui.button(
            "frmInner/btnStart",
            "START CAMPAIGN",
            "new_game.start",
            enabled=bool(selected_country_id),
            dynamic_enabled=True,
            tooltip="Start the selected OpenPower scenario as this country.",
        ):
            on_start()

    def _draw_source_frames(self, ui: GMLWidgets) -> None:
        for slot in (
            "frmInner",
            "frmInner/frmCountrySelection",
            "frmInner/frmSphereControl",
            "frmInner/frmGoals",
            "frmInner/frmSphereControl/frmControlPolitics",
            "frmInner/frmSphereControl/frmControlEconomy",
            "frmInner/frmSphereControl/frmControlMilitary",
            *(f"frmInner/frmGoals/frmTog{index}" for index in range(1, 6)),
        ):
            ui.frame(slot)

    def _render_sphere_summary(
        self,
        ui: GMLWidgets,
        scenario_preview: CampaignScenarioPreview,
        country_selected: bool,
    ) -> None:
        ui.text_at("frmInner/frmSphereControl/lblTitle", "COUNTRY CONTROL")
        for label, source_label, value_slot in (
            ("Politics", "txtPolitics", "frmControlPolitics"),
            ("Economy", "txtEconomy", "frmControlEconomy"),
            ("Military", "txtMilitary", "frmControlMilitary"),
        ):
            ui.text_at(
                f"frmInner/frmSphereControl/{source_label}",
                label,
            )
            ui.text_at(
                f"frmInner/frmSphereControl/{value_slot}",
                "OpenPower" if country_selected else "—",
                color=GAMETHEME.colors.text_main if country_selected else GAMETHEME.colors.text_dim,
                tooltip=(
                    f"Scenario scope: {scenario_preview.scope}. OpenPower has no separate REFERENCE human/computer sphere assignment."
                ),
            )

    def _render_objectives(
        self,
        ui: GMLWidgets,
        scenario_preview: CampaignScenarioPreview,
    ) -> None:
        ui.text_at("frmInner/frmGoals/lblGoals", "OBJECTIVES")
        time_label = (
            f"{scenario_preview.max_duration_minutes} min"
            if scenario_preview.max_duration_minutes
            else "No limit"
        )
        ui.text_at(
            "frmInner/frmGoals/lblTimeLimit",
            time_label,
            color=GAMETHEME.colors.text_dim,
            tooltip="Maximum campaign duration configured by the selected scenario.",
        )
        for index, toggle_slot, title_slot, deadline_slot in self._GOAL_ROWS:
            objective_index = index - 1
            if objective_index < len(scenario_preview.objectives):
                objective = scenario_preview.objectives[objective_index]
                title = objective.title
                deadline = _compact_deadline(objective.deadline)
                marker = "✓"
                color = GAMETHEME.colors.text_main
            else:
                title = "No configured objectives" if not scenario_preview.objectives and index == 1 else ""
                deadline = ""
                marker = ""
                color = GAMETHEME.colors.text_dim
            ui.text_at(toggle_slot, marker, color=GAMETHEME.colors.accent)
            ui.text_at(
                title_slot,
                title,
                color=color,
                test_id=f"new_game.objective.{index}",
            )
            ui.text_at(deadline_slot, deadline, color=GAMETHEME.colors.text_dim)


def _compact_deadline(value: str) -> str:
    if value.startswith("within ") and value.endswith(" minute(s)"):
        minutes = value.removeprefix("within ").removesuffix(" minute(s)")
        return f"{minutes} min"
    if value.startswith("game minute "):
        return value.removeprefix("game minute ") + " min"
    return "—" if value == "no deadline" else value
