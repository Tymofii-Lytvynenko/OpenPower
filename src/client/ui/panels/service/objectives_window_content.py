from __future__ import annotations

from contextlib import contextmanager
from typing import Callable

from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import active_gml_layout
from src.client.ui.panels.service.campaign_presenter import CampaignOverview, CampaignPresenter


class ObjectivesWindowContent:
    """Render campaign details in the source Objectives_Window GML slots."""

    def __init__(self) -> None:
        self._active_tab = 0

    def render(
        self,
        overview: CampaignOverview,
        country_tag: str,
        now: int,
        render_openpower_advice: Callable[[], None],
    ) -> None:
        ui = GMLWidgets("Objectives_Window")
        self._draw_source_frames(ui)
        self._render_campaign_header(ui, overview, country_tag)

        session = active_gml_layout()
        tabs_path = ui.path("frmInner/frmInner/tabInfo")
        tab_layout = session.apply_tab_page_runtime_geometry(tabs_path) if session else None
        if tab_layout is not None:
            self._render_tabs(ui, session, tabs_path, tab_layout)

        if self._active_tab == 0:
            self._render_description_tab(ui, overview)
        elif self._active_tab == 1:
            self._render_goals_tab(ui, overview, now)
        else:
            self._render_tips_tab(ui, render_openpower_advice)

    @staticmethod
    def _draw_source_frames(ui: GMLWidgets) -> None:
        for slot in (
            "frmInner",
            "frmInner/frmInner",
            "frmInner/frmInner/frmInfo",
            "frmInner/frmInner/tabInfo",
        ):
            ui.frame(slot)

    @staticmethod
    def _render_campaign_header(ui: GMLWidgets, overview: CampaignOverview, country_tag: str) -> None:
        scenario = overview.scenario or {}
        title = str(scenario.get("title") or (overview.campaign or {}).get("scenario_id") or "No active campaign")
        ui.text_at("frmInner/frmInner/frmInfo/lblTitle", "SCENARIO")
        ui.text_at(
            "frmInner/frmInner/frmInfo/txtTitle",
            title,
            tooltip=title,
            test_id="objectives.header.scenario",
        )
        ui.text_at("frmInner/frmInner/frmInfo/lblCountry", "COUNTRY")
        ui.text_at(
            "frmInner/frmInner/frmInfo/txtCountry",
            str(country_tag or "—"),
            test_id="objectives.header.country",
        )

    def _render_tabs(self, ui, session, tabs_path: str, tab_layout) -> None:
        group_rect = session.rect_for(tabs_path)
        if group_rect is None:
            return

        labels = ("DESCRIPTION", "OBJECTIVES", "TIPS")
        test_ids = (
            "objectives.tab.description",
            "objectives.tab.goals",
            "objectives.tab.tips",
        )
        if len(labels) != len(tab_layout.tab_names):
            return

        with self._source_font():
            for index, (label, test_id) in enumerate(zip(labels, test_ids, strict=True)):
                rect = session.tab_button_rect(tabs_path, index)
                if rect is None:
                    continue
                imgui.push_style_color(
                    imgui.Col_.button,
                    GAMETHEME.colors.interaction_active
                    if index == self._active_tab else GAMETHEME.colors.bg_input,
                )
                try:
                    if ui.button_at(
                        "frmInner/frmInner/tabInfo",
                        label,
                        test_id,
                        offset=(rect.x - group_rect.x, rect.y - group_rect.y),
                        size=(rect.width, rect.height),
                        padding=(1.0, 0.0),
                    ):
                        self._active_tab = index
                finally:
                    imgui.pop_style_color()

    def _render_description_tab(self, ui: GMLWidgets, overview: CampaignOverview) -> None:
        slot = "frmInner/frmInner/tabInfo/Tab1/frmInner"
        ui.frame(slot)
        if not self._begin_source_child(ui, slot, "objectives.description.page"):
            imgui.end_child()
            return

        with self._source_font():
            campaign = overview.campaign
            scenario = overview.scenario or {}
            description = str(scenario.get("description") or "")
            if description:
                imgui.text_wrapped(description, test_id="objectives.description.text")
            else:
                imgui.text_disabled(
                    "No campaign description is available.",
                    test_id="objectives.description.empty",
                )

            imgui.separator()
            if campaign:
                outcome = str(campaign.get("outcome") or "ongoing").replace("_", " ").title()
                imgui.text_colored(
                    GAMETHEME.colors.positive
                    if outcome in {"Victory", "Sandbox"} else GAMETHEME.colors.info,
                    f"Campaign status: {outcome}",
                )
                if campaign.get("outcome_reason"):
                    imgui.text_wrapped(str(campaign["outcome_reason"]))
                if campaign.get("sandbox_continuation"):
                    imgui.text_disabled("Sandbox continuation is enabled.")
            else:
                imgui.text_disabled("No campaign is active for this country.")
        imgui.end_child()

    def _render_goals_tab(self, ui: GMLWidgets, overview: CampaignOverview, now: int) -> None:
        frame_slot = "frmInner/frmInner/tabInfo/Tab2/frmObjectives"
        ui.frame(frame_slot)
        ui.text_at(
            "frmInner/frmInner/tabInfo/Tab2/frmObjectives/lblGoals",
            "OBJECTIVES",
            test_id="objectives.goals.label",
        )

        campaign = overview.campaign
        scenario = overview.scenario or {}
        remaining = self._campaign_minutes_remaining(campaign, scenario, now)
        if remaining is not None:
            ui.text_at(
                "frmInner/frmInner/tabInfo/Tab2/frmObjectives/lblTimeLimit",
                self._format_duration(remaining),
                offset=(-102.0, 0.0),
                max_width=96.0,
                color=GAMETHEME.colors.text_dim,
                test_id="objectives.goals.time_remaining",
            )
        ui.text_at(
            "frmInner/frmInner/tabInfo/Tab2/frmObjectives/lblTimeLimit",
            "TIME LIMIT" if remaining is not None else "NO TIME LIMIT",
            test_id="objectives.goals.time_limit_label",
        )

        list_slot = "frmInner/frmInner/tabInfo/Tab2/frmObjectives/lstGoals"
        if not self._begin_source_child(ui, list_slot, "objectives.goals.list"):
            imgui.end_child()
            return
        with self._source_font():
            if not overview.objectives:
                imgui.text_disabled(
                    "This campaign has no configured objectives.",
                    test_id="objectives.goals.empty",
                )
            else:
                for row in overview.objectives:
                    self._render_objective(row, now)
        imgui.end_child()

    def _render_tips_tab(self, ui: GMLWidgets, render_openpower_advice: Callable[[], None]) -> None:
        slot = "frmInner/frmInner/tabInfo/Tab3/frmInner"
        ui.frame(slot)
        if not self._begin_source_child(ui, slot, "objectives.tips.page"):
            imgui.end_child()
            return

        with self._source_font():
            imgui.text_disabled(
                "No scenario-authored tips are stored in OpenPower.",
                test_id="objectives.tips.unavailable",
            )
            render_openpower_advice()
        imgui.end_child()

    @staticmethod
    @contextmanager
    def _source_font():
        style = imgui.get_style()
        scale = max(0.1, float(style.font_scale_main) * float(style.font_scale_dpi))
        imgui.push_font(None, 9.0 / scale)
        try:
            yield
        finally:
            imgui.pop_font()

    @staticmethod
    def _begin_source_child(ui: GMLWidgets, slot: str, test_id: str) -> bool:
        rect = ui.rect(slot)
        if rect is None:
            return False
        return imgui.begin_child(
            f"##{test_id}",
            (rect.width, rect.height),
            True,
            test_id=test_id,
            gml_id=ui.path(slot),
        )

    @staticmethod
    def _campaign_minutes_remaining(campaign, scenario, now: int) -> int | None:
        if not campaign or not scenario:
            return None
        limit = int(scenario.get("max_duration_minutes") or 0)
        if limit <= 0:
            return None
        start = int(campaign.get("started_at_minute") or 0)
        return max(0, start + limit - now)

    @staticmethod
    def _format_duration(minutes: int) -> str:
        days, remaining_minutes = divmod(max(0, minutes), 1440)
        hours = remaining_minutes // 60
        return f"{days}d {hours}h" if days else f"{hours}h"

    @staticmethod
    def _render_objective(row: dict, now: int) -> None:
        title = str(row.get("title") or "Objective")
        status = str(row.get("status") or "pending").upper()
        progress = max(0.0, min(100.0, float(row.get("progress") or 0.0) * 100.0))
        color = GAMETHEME.colors.positive if status == "COMPLETED" else GAMETHEME.colors.info

        objective_id = str(row.get("id") or title)
        ObjectivesWindowContent._render_completion_indicator(objective_id, status)
        imgui.same_line()
        imgui.text_wrapped(title, test_id=f"objectives.goal.title.{objective_id}")
        imgui.text_colored(color, f"Status: {status}")
        ObjectivesWindowContent._render_objective_details(row, now, objective_id)
        Prims.meter("", progress, color)
        imgui.dummy((0.0, 6.0))

    @staticmethod
    def _render_completion_indicator(objective_id: str, status: str) -> None:
        # The source completion toggle communicates status only; objective rows remain read-only.
        imgui.begin_disabled()
        try:
            imgui.checkbox(
                f"##objective-complete:{objective_id}",
                status == "COMPLETED",
                test_id=f"objectives.goal.completed.{objective_id}",
            )
        finally:
            imgui.end_disabled()

    @staticmethod
    def _render_objective_details(row: dict, now: int, objective_id: str) -> None:
        ObjectivesWindowContent._render_description(row)
        ObjectivesWindowContent._render_values(row)
        ObjectivesWindowContent._render_deadline(row, now, objective_id)
        ObjectivesWindowContent._render_hold_duration(row)
        ObjectivesWindowContent._render_blocked_reason(row)
        ObjectivesWindowContent._render_latest_evidence(row)

    @staticmethod
    def _render_description(row: dict) -> None:
        description = str(row.get("description") or "")
        if description:
            imgui.push_text_wrap_pos(0.0)
            imgui.text_colored(GAMETHEME.colors.text_dim, description)
            imgui.pop_text_wrap_pos()

    @staticmethod
    def _render_values(row: dict) -> None:
        current = float(row.get("current_value") or 0.0)
        target = float(row.get("target_value") or 0.0)
        remaining = float(row.get("remaining") or 0.0)
        if row.get("objective_type"):
            imgui.text_disabled(f"Current {current:,.2f} / target {target:,.2f}; remaining {remaining:,.2f}")

    @staticmethod
    def _render_deadline(row: dict, now: int, objective_id: str) -> None:
        deadline = int(row.get("deadline_at_minute", -1))
        if deadline >= 0:
            imgui.text_disabled(
                f"Deadline: {max(0, deadline - now) // 1440} day(s) remaining",
                test_id=f"objectives.goal.deadline.{objective_id}",
            )

    @staticmethod
    def _render_hold_duration(row: dict) -> None:
        if int(row.get("hold_duration_minutes") or 0) > 0:
            imgui.text_disabled(
                f"Held {int(row.get('held_minutes') or 0)} / {int(row.get('hold_duration_minutes') or 0)} minute(s)"
            )

    @staticmethod
    def _render_blocked_reason(row: dict) -> None:
        status = str(row.get("status") or "pending").upper()
        if status == "BLOCKED":
            imgui.text_colored(
                GAMETHEME.colors.warning,
                str(row.get("missing_data_reason") or row.get("reason") or "Required data is missing."),
            )
        elif row.get("reason"):
            imgui.text_disabled(str(row.get("reason")))

    @staticmethod
    def _render_latest_evidence(row: dict) -> None:
        evidence = CampaignPresenter.latest_evidence(row)
        if evidence:
            source = str(evidence.get("source_table") or "campaign state")
            minute = int(evidence.get("game_minute") or 0)
            imgui.text_disabled(
                f"Latest evidence: {source} at minute {minute} "
                f"({float(evidence.get('current_value') or 0.0):,.2f} / "
                f"{float(evidence.get('target_value') or 0.0):,.2f})"
            )
