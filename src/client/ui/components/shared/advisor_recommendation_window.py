"""Present one authoritative advisor recommendation in the REFERENCE source window."""
from __future__ import annotations

from src.client.services.network_client_service import NetworkClient
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.theme import GAMETHEME, with_alpha
from src.client.ui.layouts.gml_layout import active_gml_layout
from src.client.ui.panels.service.campaign_presenter import CampaignPresenter
from src.shared.actions import ActionResolveAdvisorRecommendation


_WINDOW_ID = "advisor.recommendation.window"
_GML_TEMPLATE = "Advisor_Window"
_BASE_SIZE = (319.0, 250.0)
_ACTION_ROW_SIZE = (266.0, 34.0)
_ACTION_ROW_GROWTH = 49.0
_RESULT_NORMALIZATION = 5.0


class AdvisorRecommendationWindow:
    """Queue native OpenPower recommendations inside the source advisor canvas."""

    def __init__(self, net_client: NetworkClient, country_tag: str) -> None:
        self._net = net_client
        self._country_tag = str(country_tag or "").strip().upper()
        self._presenter = CampaignPresenter()
        self._requested_id = ""
        self._queued_ids: list[str] = []
        self._submitted_ids: set[str] = set()
        self._focus_requested = False

    def open(self, recommendation: dict) -> bool:
        """Start a source-style review sequence at the selected native record."""
        if self._queued_ids or self._requested_id:
            return False
        recommendation_id = str(recommendation.get("id") or "").strip()
        if not recommendation_id:
            return False
        self._requested_id = recommendation_id
        self._focus_requested = True
        return True

    def render(self, state) -> None:
        if not self._country_tag:
            return

        overview = self._presenter.build_overview(state, self._country_tag)
        actionable = {
            str(item.get("id") or ""): item
            for item in overview.recommendations
            if self._presenter.recommendation_action_label(item)
        }
        active_ids = set(actionable)
        self._submitted_ids.intersection_update(active_ids)

        if self._requested_id:
            selected = actionable.get(self._requested_id)
            if selected is not None:
                self._queued_ids = [self._requested_id] + [
                    recommendation_id
                    for recommendation_id in actionable
                    if recommendation_id != self._requested_id
                ]
            self._requested_id = ""

        self._queued_ids = [
            recommendation_id
            for recommendation_id in self._queued_ids
            if recommendation_id in actionable and recommendation_id not in self._submitted_ids
        ]
        if not self._queued_ids:
            return

        recommendation = actionable[self._queued_ids[0]]
        self._render_recommendation(recommendation)

    def _render_recommendation(self, recommendation: dict) -> None:
        recommendation_id = str(recommendation.get("id") or "")
        action_label = self._presenter.recommendation_action_label(recommendation)
        row_growth = _ACTION_ROW_GROWTH - _RESULT_NORMALIZATION
        window_size = (_BASE_SIZE[0], _BASE_SIZE[1] + row_growth)
        viewport = imgui.get_main_viewport()
        x = float(viewport.pos.x + (viewport.size.x - window_size[0]) / 2.0)
        y = float(viewport.pos.y + (viewport.size.y - window_size[1]) / 2.0)
        flags = (
            imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_scrollbar
            | imgui.WindowFlags_.no_scroll_with_mouse
        )
        resolved = None
        if self._focus_requested:
            imgui.set_next_window_focus()
            self._focus_requested = False

        with WindowManager.window(
            "ADVISOR RECOMMENDATION##advisor.recommendation.window",
            x=x,
            y=y,
            w=window_size[0],
            h=window_size[1],
            flags=flags,
            test_id=_WINDOW_ID,
            gml_template=_GML_TEMPLATE,
            size_override=window_size,
            avoid_overlaps=True,
        ) as opened:
            if not opened:
                resolved = False
            else:
                self._apply_source_plan_geometry(row_growth)
                ui = GMLWidgets(f"{_GML_TEMPLATE}/frmInner")
                for slot in ("frmProblem", "frmPlan", "frmResult"):
                    ui.frame(slot)

                ui.text("frmProblem/lblTitle", "PROBLEM")
                title = str(recommendation.get("title") or "Advisor recommendation").strip()
                reason = str(recommendation.get("reason") or "").strip()
                problem = f"{title}\n{reason}" if reason else title
                self._wrapped_text(
                    ui,
                    "frmProblem/txtProblem",
                    problem,
                    f"advisor.recommendation.problem.{recommendation_id}",
                )

                ui.text("frmPlan/lblTitle", "PLAN")
                self._draw_action_row(ui, action_label, recommendation)

                ui.text("frmResult/lblTitle", "RESULT")
                self._wrapped_text(
                    ui,
                    "frmResult/frmResults/txtResult",
                    "Pending your decision. The proposed action has not been applied.",
                    f"advisor.recommendation.result.{recommendation_id}",
                )

                clicked = ui.button(
                    "btnExecute",
                    "Execute",
                    f"advisor.recommendation.execute.{recommendation_id}",
                )
                button_rect = ui.rect("btnExecute")
                session = active_gml_layout()
                mouse_pos = imgui.get_mouse_pos()
                # The source bottom anchor can land outside ImGui's item-hover region;
                # keep its visible GML rectangle clickable in that case.
                source_slot_clicked = bool(
                    session is not None
                    and button_rect is not None
                    and imgui.is_mouse_clicked(imgui.MouseButton_.left)
                    and imgui.is_window_hovered()
                    and session.window_position[0] + button_rect.x <= mouse_pos.x
                    <= session.window_position[0] + button_rect.x + button_rect.width
                    and session.window_position[1] + button_rect.y <= mouse_pos.y
                    <= session.window_position[1] + button_rect.y + button_rect.height
                )
                if clicked or source_slot_clicked:
                    resolved = True

        if resolved is not None:
            self._resolve(recommendation_id, resolved)

    @staticmethod
    def _apply_source_plan_geometry(row_growth: float) -> None:
        session = active_gml_layout()
        if session is None:
            return

        # REFERENCE adds a 49 px action row, then trims the completed plan window by 5 px.
        session.resize_component("Advisor_Window/frmInner", height=217.0 + row_growth)
        session.resize_component("Advisor_Window/frmInner/frmPlan", height=23.0 + row_growth)
        session.resize_component("Advisor_Window/picBlueGradient", height=243.0 + row_growth)
        session.resize_component("Advisor_Window/picShadowGradient", height=243.0 + row_growth)
        session.move_subtree("Advisor_Window/frmInner/frmResult", y=row_growth)
        session.move_subtree("Advisor_Window/frmInner/btnExecute", y=row_growth)

    @staticmethod
    def _draw_action_row(ui: GMLWidgets, action_label: str, recommendation: dict) -> None:
        session = active_gml_layout()
        plan = ui.rect("frmPlan")
        if session is None or plan is None:
            return

        x = session.window_position[0] + plan.x + 6.0 - imgui.get_scroll_x()
        y = session.window_position[1] + plan.y + 21.0 - imgui.get_scroll_y()
        right = (x + _ACTION_ROW_SIZE[0], y + _ACTION_ROW_SIZE[1])
        draw = imgui.get_window_draw_list()
        draw.add_rect_filled(
            (x, y),
            right,
            imgui.get_color_u32(GAMETHEME.colors.panel_bg_dark),
        )
        draw.add_rect(
            (x, y),
            right,
            imgui.get_color_u32(with_alpha(GAMETHEME.colors.text_dim, 0.35)),
            0.0,
            flags=0,
            thickness=1.0,
        )

        ui.text_at(
            "frmPlan",
            action_label,
            offset=(9.0, 21.0),
            max_width=250.0,
            font_size=9.0,
            test_id=f"advisor.recommendation.action.{recommendation.get('id', '')}",
        )
        target = str(
            recommendation.get("affected_country_id")
            or recommendation.get("actor_country_id")
            or ""
        ).strip().upper()
        if target:
            ui.text_at(
                "frmPlan",
                f"Target: {target}",
                offset=(39.0, 37.0),
                max_width=230.0,
                font_size=9.0,
                color=GAMETHEME.colors.text_dim,
                test_id=f"advisor.recommendation.target.{recommendation.get('id', '')}",
            )

    @staticmethod
    def _wrapped_text(ui: GMLWidgets, slot: str, value: str, test_id: str) -> None:
        session = active_gml_layout()
        component = session.layout.component(ui.path(slot)) if session else None
        rect = ui.rect(slot)
        if session is None or component is None or rect is None:
            return

        x = session.window_position[0] + rect.x - imgui.get_scroll_x()
        y = session.window_position[1] + rect.y - imgui.get_scroll_y()
        draw = imgui.get_window_draw_list()
        font_pushed = component.font_size is not None
        if font_pushed:
            style = imgui.get_style()
            scale = max(0.1, float(style.font_scale_main) * float(style.font_scale_dpi))
            imgui.push_font(None, float(component.font_size) / scale)
        draw.push_clip_rect((x, y), (x + rect.width, y + rect.height), True)
        imgui.push_text_wrap_pos(
            x + component.text_offset[0] + rect.width - abs(component.text_offset[0])
        )
        try:
            imgui.text_wrapped(value, gml_id=ui.path(slot), test_id=test_id)
        finally:
            imgui.pop_text_wrap_pos()
            draw.pop_clip_rect()
            if font_pushed:
                imgui.pop_font()

    def _resolve(self, recommendation_id: str, accept: bool) -> None:
        if not recommendation_id or recommendation_id in self._submitted_ids:
            return
        self._submitted_ids.add(recommendation_id)
        if recommendation_id in self._queued_ids:
            self._queued_ids.remove(recommendation_id)
        self._net.send_action(ActionResolveAdvisorRecommendation(
            player_id=self._net.player_id,
            recommendation_id=recommendation_id,
            accept=accept,
        ))
