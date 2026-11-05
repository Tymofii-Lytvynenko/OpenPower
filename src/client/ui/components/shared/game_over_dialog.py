"""Campaign outcome dialog using OpenPower objective state and the REFERENCE frame."""
from __future__ import annotations

from collections.abc import Callable

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.layouts.gml_layout import gml_child_frame
from src.client.ui.layouts.gml_rows import gml_row
from src.client.ui.panels.service.campaign_presenter import CampaignPresenter


_TERMINAL_OUTCOMES = frozenset({"victory", "defeat", "draw"})
_RESULT_OBJECTIVE_STATES = frozenset({"completed", "failed", "expired"})


class GameOverDialog:
    """Show a terminal, non-sandbox campaign result and its recorded objectives."""

    def __init__(self) -> None:
        self._presenter = CampaignPresenter()
        self._dismissed_result: str | None = None

    def is_game_over(self, state, country_tag: str) -> bool:
        campaign = self._presenter.latest_campaign(state, country_tag)
        outcome = str((campaign or {}).get("outcome") or "ongoing").strip().casefold()
        return (
            campaign is not None
            and outcome in _TERMINAL_OUTCOMES
            and not bool(campaign.get("sandbox_continuation"))
        )

    def render(
        self,
        state,
        country_tag: str,
        *,
        on_return_to_menu: Callable[[], None],
    ) -> bool:
        overview = self._presenter.build_overview(state, country_tag)
        campaign = overview.campaign
        outcome = str((campaign or {}).get("outcome") or "ongoing").strip().casefold()
        if (
            campaign is None
            or outcome not in _TERMINAL_OUTCOMES
            or bool(campaign.get("sandbox_continuation"))
        ):
            self._dismissed_result = None
            return False

        result_key = f"{campaign.get('id', '')}:{outcome}"
        if self._dismissed_result == result_key:
            return False

        layout = imgui.get_main_viewport().size
        title = "SCENARIO COMPLETED" if outcome == "victory" else "GAME OVER"
        with WindowManager.window(
            title,
            x=(float(layout.x) - 503.0) / 2.0,
            y=(float(layout.y) - 273.0) / 2.0,
            w=503.0,
            h=273.0,
            flags=imgui.WindowFlags_.no_resize,
            test_id="game_over.dialog",
            gml_template="Game_Over_Window",
        ) as opened:
            if not opened:
                self._finish(result_key, on_return_to_menu)
                return False

            ui = GMLWidgets("Game_Over_Window")
            for slot in ("frmInner", "frmInner/frmText", "frmInner/frmObjectives"):
                ui.frame(slot)

            summary = str(campaign.get("outcome_reason") or "The campaign has ended.")
            self._render_summary(ui, summary)
            ui.text("frmInner/frmObjectives/lblTitle", "OBJECTIVES")
            self._render_objectives(
                state,
                ui,
                overview.objectives,
                int(campaign.get("started_at_minute") or 0),
            )

            if ui.button(
                "frmInner/btnMainMenu",
                "MAIN MENU",
                "game_over.main_menu",
                tooltip="Stop this campaign and return to the main menu.",
            ):
                self._finish(result_key, on_return_to_menu)
        return True

    @staticmethod
    def _render_summary(ui: GMLWidgets, summary: str) -> None:
        with gml_child_frame(
            ui.path("frmInner/frmText"),
            padding=(6.0, 6.0),
            bordered=False,
            test_id="game_over.summary_frame",
        ) as opened:
            if not opened:
                return
            # The child frame suspends its parent GML session, so use the label's
            # extracted inset and width relative to that source-sized frame.
            imgui.set_cursor_pos((9.0, 6.0))
            style = imgui.get_style()
            font_scale = max(0.1, float(style.font_scale_main) * float(style.font_scale_dpi))
            imgui.push_font(None, 9.0 / font_scale)
            imgui.push_text_wrap_pos(imgui.get_cursor_pos_x() + 448.0)
            try:
                imgui.text_wrapped(
                    summary,
                    test_id="game_over.summary",
                )
            finally:
                imgui.pop_text_wrap_pos()
                imgui.pop_font()

    @staticmethod
    def _render_objectives(state, ui: GMLWidgets, objectives, started_at: int) -> None:
        with gml_child_frame(
            ui.path("frmInner/frmObjectives/lstObjectives"),
            padding=(0.0, 0.0),
            bordered=False,
            test_id="game_over.objectives",
        ) as opened:
            if not opened:
                return

            rows = [
                row for row in objectives
                if str(row.get("status") or "active").strip().casefold()
                in _RESULT_OBJECTIVE_STATES
            ]
            rows.sort(key=lambda row: (
                str(row.get("status") or "").casefold() != "completed",
                str(row.get("id") or ""),
            ))
            if not rows:
                imgui.set_cursor_pos((2.0, 2.0))
                imgui.text_disabled("No completed or timed-out objectives.", test_id="game_over.objectives.empty")
                return

            for row in rows:
                objective_id = str(row.get("id") or row.get("title") or "objective")
                status = str(row.get("status") or "").strip().upper()
                title = str(row.get("title") or "Objective")
                deadline = int(row.get("deadline_at_minute") or -1)
                duration = "No deadline" if deadline < 0 else f"{max(0, deadline - started_at) // 1440} day(s)"
                with gml_row("lstGoalItem", objective_id, width=435.0) as row_ui:
                    row_ui.text(
                        "txtName",
                        title,
                        tooltip=title,
                        test_id=f"game_over.objective.{objective_id}.name",
                    )
                    row_ui.text(
                        "txtTime",
                        duration,
                        tooltip="Duration calculated from the campaign's OpenPower deadline.",
                        test_id=f"game_over.objective.{objective_id}.time",
                    )
                    row_ui.text(
                        "txtSuccess",
                        status,
                        test_id=f"game_over.objective.{objective_id}.status",
                    )

    def _finish(self, result_key: str, on_return_to_menu: Callable[[], None]) -> None:
        self._dismissed_result = result_key
        on_return_to_menu()
