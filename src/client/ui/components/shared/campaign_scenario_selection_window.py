from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from src.client.services.campaign_selection import preview_campaign_scenario
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.theme import GAMETHEME


class CampaignScenarioSelectionWindow:
    """Render OpenPower campaign scenarios in the source REFERENCE scenario window."""

    def __init__(self) -> None:
        self._active_detail = "description"

    _ROOT = "Scenarios_Window"
    _DIFFICULTY_ROWS = (
        ("Politics", "frmInner/frmGolem/txtPolitics", (
            "frmInner/frmGolem/togPoliticBeginner",
            "frmInner/frmGolem/togPoliticIntermediate",
            "frmInner/frmGolem/togPoliticExpert",
        )),
        ("Economy", "frmInner/frmGolem/txtEconomy", (
            "frmInner/frmGolem/togEconomicBeginner",
            "frmInner/frmGolem/togEconomicIntermediate",
            "frmInner/frmGolem/togEconomicExpert",
        )),
        ("Military", "frmInner/frmGolem/txtMilitary", (
            "frmInner/frmGolem/togMilitaryBeginner",
            "frmInner/frmGolem/togMilitaryIntermediate",
            "frmInner/frmGolem/togMilitaryExpert",
        )),
    )

    def render(
        self,
        screen_width: float,
        screen_height: float,
        scenarios: Sequence[Mapping[str, object]],
        selected_scenario_id: str | None,
        on_select: Callable[[str], None],
        on_continue: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        window_open = True
        with WindowManager.window(
            "SELECT SCENARIO",
            x=(float(screen_width) - 560.0) / 2.0,
            y=(float(screen_height) - 354.0) / 2.0,
            w=560,
            h=354,
            test_id="new_game.scenario.dialog",
            gml_template=self._ROOT,
            follow_position=True,
        ) as window_open:
            if window_open:
                self._render_content(
                    scenarios,
                    selected_scenario_id,
                    on_select,
                    on_continue,
                    on_cancel,
                )
        if not window_open:
            on_cancel()

    def _render_content(
        self,
        scenarios: Sequence[Mapping[str, object]],
        selected_scenario_id: str | None,
        on_select: Callable[[str], None],
        on_continue: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        ui = GMLWidgets(self._ROOT)
        self._draw_source_frames(ui)
        self._render_unavailable_difficulty_presets(ui)
        selected = next(
            (
                scenario for scenario in scenarios
                if str(scenario.get("id") or "") == str(selected_scenario_id or "")
            ),
            None,
        )
        self._render_scenario_list(ui, scenarios, selected_scenario_id, on_select)
        self._render_details(ui, selected)

        can_continue = selected is not None
        if ui.button(
            "frmInner/btnStart",
            "CONTINUE",
            "new_game.scenario.continue",
            enabled=can_continue,
            dynamic_enabled=True,
        ):
            on_continue()
        if ui.button("frmInner/btnCancel", "CANCEL", "new_game.scenario.cancel"):
            on_cancel()

    def _draw_source_frames(self, ui: GMLWidgets) -> None:
        for slot in (
            "frmInner",
            "frmInner/frmGolem",
            "frmInner/frmCustom",
            "frmInner/frmScenario",
            "frmInner/frmScenario/frmInfo",
            "frmInner/frmScenario/tabInfo",
        ):
            ui.frame(slot)

    def _render_unavailable_difficulty_presets(self, ui: GMLWidgets) -> None:
        for label, label_slot, preset_slots in self._DIFFICULTY_ROWS:
            ui.text_at(
                label_slot,
                label,
                color=GAMETHEME.colors.text_main,
            )
            for preset_slot in preset_slots:
                ui.text_at(
                    preset_slot,
                    "N/A",
                    color=GAMETHEME.colors.text_dim,
                    tooltip="OpenPower campaign scenarios do not use REFERENCE sphere difficulty presets.",
                )

    def _render_scenario_list(
        self,
        ui: GMLWidgets,
        scenarios: Sequence[Mapping[str, object]],
        selected_scenario_id: str | None,
        on_select: Callable[[str], None],
    ) -> None:
        ui.text_at("frmInner/frmCustom/lblTitle", "CAMPAIGN SCENARIOS")
        opened = imgui.begin_child(
            "##campaign_scenarios",
            (189.0, 76.0),
            True,
            test_id="new_game.scenario.list",
            gml_id=ui.path("frmInner/frmCustom/lstCustom"),
        )
        if opened:
            for scenario in scenarios:
                scenario_id = str(scenario.get("id") or "").strip()
                if not scenario_id:
                    continue
                title = str(scenario.get("title") or scenario_id)
                if imgui.selectable(
                    f"{title}##scenario-{scenario_id}",
                    scenario_id == str(selected_scenario_id or ""),
                    test_id=f"new_game.scenario.{scenario_id}",
                )[0]:
                    on_select(scenario_id)
            if not scenarios:
                _text_disabled_wrapped(
                    "No enabled scenarios are available.",
                    test_id="new_game.scenario.empty_list",
                )
        imgui.end_child()

    def _render_details(
        self,
        ui: GMLWidgets,
        scenario: Mapping[str, object] | None,
    ) -> None:
        name = str(scenario.get("title") or scenario.get("id") or "") if scenario else ""
        country_ids = _scenario_country_ids(scenario)
        ui.text_at("frmInner/frmScenario/frmInfo/lblTitle", "SCENARIO")
        ui.text_at("frmInner/frmScenario/frmInfo/txtTitle", name or "Select a scenario")
        ui.text_at("frmInner/frmScenario/frmInfo/lblCountry", "COUNTRIES")
        ui.text_at(
            "frmInner/frmScenario/frmInfo/txtCountry",
            ", ".join(country_ids) if country_ids else "All playable countries",
            tooltip="Eligible countries are filtered from OpenPower scenario data.",
        )

        opened = imgui.begin_child(
            "##scenario_detail_tabs",
            (314.0, 243.0),
            False,
            test_id="new_game.scenario.details",
            gml_id=ui.path("frmInner/frmScenario/tabInfo"),
        )
        if not opened:
            imgui.end_child()
            return

        for key, label, test_id in (
            ("description", "DESCRIPTION", "new_game.scenario.tab.description"),
            ("objectives", "OBJECTIVES", "new_game.scenario.tab.objectives"),
            ("rules", "RULES", "new_game.scenario.tab.rules"),
        ):
            if imgui.button(label, (96.0, 18.0), test_id=test_id):
                self._active_detail = key
            if key != "rules":
                imgui.same_line()
        imgui.separator()
        if self._active_detail == "description":
            self._render_description_tab(scenario)
        elif self._active_detail == "objectives":
            self._render_objectives_tab(scenario)
        else:
            self._render_rules_tab(scenario)
        imgui.end_child()

    def _render_description_tab(self, scenario: Mapping[str, object] | None) -> None:
        if scenario is None:
            _text_disabled_wrapped(
                "Select an enabled campaign scenario to view its details.",
                test_id="new_game.scenario.empty_details",
            )
        else:
            description = str(scenario.get("description") or "No scenario description is available.")
            imgui.text_wrapped(description, test_id="new_game.scenario.description")
            preview = preview_campaign_scenario(scenario)
            imgui.separator()
            imgui.text(f"Scope: {preview.scope}")
            if preview.max_duration_minutes:
                imgui.text(f"Time limit: {preview.max_duration_minutes} minutes")
            else:
                imgui.text("Time limit: none")
            imgui.text_disabled(
                "Sandbox continuation enabled"
                if bool(scenario.get("sandbox_allowed", True))
                else "Scenario outcome ends the campaign"
            )

    def _render_objectives_tab(self, scenario: Mapping[str, object] | None) -> None:
        preview = preview_campaign_scenario(scenario)
        imgui.text("GOALS", test_id="new_game.scenario.objectives.heading")
        imgui.same_line(217.0)
        time_limit = (
            f"{preview.max_duration_minutes} min"
            if preview.max_duration_minutes
            else "No limit"
        )
        imgui.text_disabled(time_limit, test_id="new_game.scenario.time_limit")
        imgui.separator()
        if preview.objectives:
            for index, objective in enumerate(preview.objectives, start=1):
                imgui.bullet_text(
                    f"{objective.title} ({objective.deadline})",
                    test_id=f"new_game.scenario.objective.{index}",
                )
        else:
            _text_disabled_wrapped(
                "This scenario has no configured objectives.",
                test_id="new_game.scenario.empty_objectives",
            )

    def _render_rules_tab(self, scenario: Mapping[str, object] | None) -> None:
        preview = preview_campaign_scenario(scenario)
        if preview.enabled_rules:
            for index, rule in enumerate(preview.enabled_rules, start=1):
                imgui.bullet_text(
                    rule.replace("_", " ").capitalize(),
                    test_id=f"new_game.scenario.rule.{index}",
                )
        else:
            _text_disabled_wrapped(
                "No optional rules are enabled.",
                test_id="new_game.scenario.empty_rules",
            )


def _text_disabled_wrapped(text: str, *, test_id: str) -> None:
    imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.text_dim)
    try:
        imgui.text_wrapped(text, test_id=test_id)
    finally:
        imgui.pop_style_color()


def _scenario_country_ids(scenario: Mapping[str, object] | None) -> list[str]:
    if scenario is None:
        return []
    import json

    raw = scenario.get("selectable_country_ids_json") or "[]"
    try:
        values = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(values, list):
        return []
    return sorted({str(value).strip().upper() for value in values if str(value).strip()})
