from __future__ import annotations

from typing import Any

import polars as pl
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
from src.client.renderers.flag_renderer import FlagRenderer
from src.client.ui.layouts.gml_layout import (
    active_gml_layout,
    get_gml_layout,
    gml_child_frame,
)
from src.client.ui.panels.military.peace_deal_editor import PeaceDealEditor
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_data import resolve_country_name
from src.shared.actions import ActionJoinWar, ActionOfferPeace


class WarListPanel:
    """Shows active wars in the source GML frame and dispatches guarded diplomacy actions."""

    _ROW_HEIGHT = 16.0

    def __init__(self) -> None:
        self._presenter = MilitaryPresenter()
        self._flag_renderer = FlagRenderer()
        self._selected_war_id: str | None = None
        self._peace_editor = PeaceDealEditor()
        self._show_peace_page = False

    def render(self, state, context: PanelRenderContext) -> bool:
        layout = get_gml_layout("War_List_Window")
        viewport = imgui.get_main_viewport().size
        x = max(0.0, (float(viewport.x) - layout.width) / 2.0)
        y = max(0.0, (float(viewport.y) - layout.height) / 2.0)
        with WindowManager.window(
            "WAR LIST",
            x=x,
            y=y,
            w=layout.width,
            h=layout.height,
            test_id="war_list.panel",
            gml_template="War_List_Window",
        ) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        title = GMLWidgets("War_List_Window/frmTitle")
        # The source hides btnApply. OpenPower uses that reserved title slot for its
        # structured peace page while keeping the source war overview intact.
        page_tooltip = (
            "Return to the active war list"
            if self._show_peace_page
            else "Open structured peace terms"
        )
        if title.button("btnApply", "", "war_list.page", tooltip=page_tooltip):
            self._show_peace_page = not self._show_peace_page
        self._draw_page_icon(title)

        wars = self._presenter.all_wars(state)
        if self._selected_war_id is None and wars:
            self._selected_war_id = str(wars[0].get("id") or "")
        selected_war = self._selected_war(wars)
        if selected_war is not None:
            self._selected_war_id = str(selected_war.get("id") or "")

        if self._show_peace_page:
            self._render_peace_page(state, selected_war, context)
            return

        self._render_war_overview(state, wars, selected_war, context)

    def _selected_war(self, wars: list[dict[str, Any]]) -> dict[str, Any] | None:
        selected = next(
            (war for war in wars if str(war.get("id") or "") == self._selected_war_id),
            None,
        )
        if selected is None and wars:
            selected = wars[0]
        return selected

    def _render_war_overview(
        self,
        state,
        wars: list[dict[str, Any]],
        selected_war: dict[str, Any] | None,
        context: PanelRenderContext,
    ) -> None:
        self._render_war_list(state, wars)
        self._render_details(state, selected_war, context)

    def _render_war_list(self, state, wars: list[dict[str, Any]]) -> None:
        labels = GMLWidgets("War_List_Window/frmInner/frmWarList")
        labels.text("txtTransparentLabel1", "COUNTRY")
        labels.text("txtTransparentLabel2", "ALLIES")
        labels.text("txtTransparentLabel4", "COUNTRY")
        labels.text("txtTransparentLabel3", "ALLIES")

        with gml_child_frame(
            labels.path("lstWar"),
            padding=(0.0, 0.0),
            bordered=True,
        ) as visible:
            if not visible:
                return
            self._render_war_rows(state, wars)

    def _render_war_rows(self, state, wars: list[dict[str, Any]]) -> None:
        origin = imgui.get_cursor_screen_pos()
        available_width = max(0.0, float(imgui.get_content_region_avail().x))
        row_width = min(492.0, available_width)
        draw = imgui.get_window_draw_list()
        label_color = imgui.get_color_u32(GAMETHEME.colors.text_main)
        dim_color = imgui.get_color_u32(GAMETHEME.colors.text_dim)
        selected_color = imgui.get_color_u32(GAMETHEME.colors.interaction_active)

        if not wars:
            imgui.set_cursor_screen_pos((origin.x + 4.0, origin.y + 3.0))
            imgui.text_disabled("No active wars")
            return

        for index, war in enumerate(wars):
            row_id = str(war.get("id") or f"war-{index}")
            row_y = float(origin.y) + index * self._ROW_HEIGHT
            imgui.set_cursor_screen_pos((origin.x, row_y))
            clicked = imgui.invisible_button(
                f"##war_row_{row_id}",
                (row_width, self._ROW_HEIGHT),
                test_id=f"war_list.select.{row_id}",
            )
            hovered = imgui.is_item_hovered()
            selected = row_id == self._selected_war_id
            if selected or hovered:
                fill = selected_color if selected else imgui.get_color_u32(
                    GAMETHEME.colors.bg_input
                )
                draw.add_rect_filled(
                    (origin.x, row_y),
                    (origin.x + row_width, row_y + self._ROW_HEIGHT),
                    fill,
                )
            if clicked:
                self._selected_war_id = row_id

            leader_a = self._tag(war.get("leader_a"))
            leader_b = self._tag(war.get("leader_b"))
            self._draw_flag_at(origin.x + 1.0, row_y + 1.0, leader_a)
            self._draw_cell(
                draw,
                origin.x + 23.0,
                row_y + 1.0,
                168.0,
                resolve_country_name(state, leader_a),
                label_color,
            )
            self._draw_cell(
                draw,
                origin.x + 194.0,
                row_y + 1.0,
                24.0,
                str(len(self._side_allies(war, "side_a", leader_a))),
                label_color,
                align="right",
            )
            self._draw_cell(draw, origin.x + 221.0, row_y + 1.0, 29.0, "vs.", dim_color)
            self._draw_flag_at(origin.x + 253.0, row_y + 1.0, leader_b)
            self._draw_cell(
                draw,
                origin.x + 275.0,
                row_y + 1.0,
                168.0,
                resolve_country_name(state, leader_b),
                label_color,
            )
            self._draw_cell(
                draw,
                origin.x + 446.0,
                row_y + 1.0,
                35.0,
                str(len(self._side_allies(war, "side_b", leader_b))),
                label_color,
                align="right",
            )

        imgui.set_cursor_screen_pos(
            (origin.x, float(origin.y) + len(wars) * self._ROW_HEIGHT)
        )

    @staticmethod
    def _draw_cell(draw, x, y, width, text: str, color, *, align: str = "left") -> None:
        display = Prims.fit_text(str(text), max(0.0, width - 2.0))
        text_width = float(imgui.calc_text_size(display).x)
        text_x = x + max(0.0, width - text_width) if align == "right" else x
        draw.add_text((text_x, y), color, display)

    def _render_details(
        self,
        state,
        war: dict[str, Any] | None,
        context: PanelRenderContext,
    ) -> None:
        ui = GMLWidgets("War_List_Window/frmInner/frmWarDetails")
        ui.text("txtTransparentLabel1", "COUNTRY")
        ui.text("txtTransparentLabel2", "STATUS")
        ui.text("txtTransparentLabel5", "vs.")
        ui.text("txtTransparentLabel4", "COUNTRY")
        ui.text("txtTransparentLabel3", "STATUS")
        if war is None:
            return

        leader_a = self._tag(war.get("leader_a"))
        leader_b = self._tag(war.get("leader_b"))
        intent_a = self._intent(war.get("intent_a"))
        intent_b = self._intent(war.get("intent_b"))
        leaders_a = GMLWidgets(ui.path("frmMasterAttacker"))
        leaders_b = GMLWidgets(ui.path("frmMasterDefender"))
        leaders_a.picture(
            "picFlag",
            lambda width, height: self._draw_flag(leader_a, width, height),
        )
        leaders_b.picture(
            "picFlag1",
            lambda width, height: self._draw_flag(leader_b, width, height),
        )
        leaders_a.text(
            "txtName",
            resolve_country_name(state, leader_a),
            max_width=170.0,
            tooltip=leader_a,
        )
        leaders_b.text(
            "txtName1",
            resolve_country_name(state, leader_b),
            max_width=170.0,
            tooltip=leader_b,
        )
        self._draw_status_marker(leaders_a, "picState", intent_a)
        self._draw_status_marker(leaders_b, "picState1", intent_b)

        side_a = self._side_allies(war, "side_a", leader_a)
        side_b = self._side_allies(war, "side_b", leader_b)
        self._render_member_list(
            state,
            ui.path("lstWar"),
            side_a,
            war,
            side_name="attacker",
        )
        self._render_member_list(
            state,
            ui.path("lstWar1"),
            side_b,
            war,
            side_name="defender",
        )
        self._render_side_actions(war, context, leader_a, leader_b, intent_a, intent_b)

    def _render_member_list(
        self,
        state,
        component_path: str,
        members: list[str],
        war: dict[str, Any],
        *,
        side_name: str,
    ) -> None:
        with gml_child_frame(
            component_path,
            padding=(1.0, 0.0),
            bordered=True,
        ) as visible:
            if not visible:
                return
            origin = imgui.get_cursor_screen_pos()
            width = float(imgui.get_content_region_avail().x)
            draw = imgui.get_window_draw_list()
            color = imgui.get_color_u32(GAMETHEME.colors.text_main)
            for index, tag in enumerate(members):
                row_y = float(origin.y) + index * self._ROW_HEIGHT
                imgui.set_cursor_screen_pos((origin.x + 1.0, row_y + 1.0))
                self._draw_flag(tag, 22.0, 13.0)
                self._draw_cell(
                    draw,
                    origin.x + 24.0,
                    row_y + 1.0,
                    max(0.0, width - 27.0),
                    resolve_country_name(state, tag),
                    color,
                )
                exhaustion = self._war_exhaustion(state, war, tag)
                if imgui.is_mouse_hovering_rect(
                    (origin.x, row_y),
                    (origin.x + width, row_y + self._ROW_HEIGHT),
                ):
                    exhaustion_text = (
                        f"{exhaustion:.0f}" if exhaustion is not None else "unknown"
                    )
                    imgui.set_tooltip(
                        f"{resolve_country_name(state, tag)} — war exhaustion {exhaustion_text}"
                    )

    def _render_side_actions(
        self,
        war: dict[str, Any],
        context: PanelRenderContext,
        leader_a: str,
        leader_b: str,
        intent_a: str,
        intent_b: str,
    ) -> None:
        country = self._tag(context.target_tag)
        if not context.is_own_country or not country:
            return
        side_a = {self._tag(tag) for tag in war.get("side_a") or []}
        side_b = {self._tag(tag) for tag in war.get("side_b") or []}
        if country in side_a or country in side_b:
            self._render_status_actions(
                context,
                "togPeace",
                "togWar",
                "attacker",
                leader_a == country,
                intent_a,
                str(war.get("id") or ""),
                country,
            )
            self._render_status_actions(
                context,
                "togPeace1",
                "togWar1",
                "defender",
                leader_b == country,
                intent_b,
                str(war.get("id") or ""),
                country,
            )
            return

        can_join = context.net_client is not None
        ui = GMLWidgets("War_List_Window/frmInner/frmWarDetails")
        if ui.button(
            "btnJoin",
            "JOIN",
            "war_list.join.attacker",
            enabled=can_join,
            tooltip="Join the attacking side",
        ) and can_join:
            context.net_client.send_action(
                ActionJoinWar(
                    player_id=context.net_client.player_id,
                    war_id=str(war.get("id") or ""),
                    source_country_tag=country,
                    side="attacker",
                )
            )
        if ui.button(
            "btnJoin1",
            "JOIN",
            "war_list.join.defender",
            enabled=can_join,
            tooltip="Join the defending side",
        ) and can_join:
            context.net_client.send_action(
                ActionJoinWar(
                    player_id=context.net_client.player_id,
                    war_id=str(war.get("id") or ""),
                    source_country_tag=country,
                    side="defender",
                )
            )

    def _render_status_actions(
        self,
        context: PanelRenderContext,
        peace_slot: str,
        war_slot: str,
        side: str,
        is_leader: bool,
        current_intent: str,
        war_id: str,
        country: str,
    ) -> None:
        ui = GMLWidgets("War_List_Window/frmInner/frmWarDetails")
        enabled = is_leader and context.net_client is not None
        if self._status_button(
            ui,
            peace_slot,
            "PEACE",
            f"war_list.peace.{side}",
            enabled,
            current_intent == "peace",
            GAMETHEME.colors.positive,
            "Offer peace for this war",
        ):
            context.net_client.send_action(
                ActionOfferPeace(
                    player_id=context.net_client.player_id,
                    war_id=war_id,
                    source_country_tag=country,
                    terms="peace",
                )
            )
        if self._status_button(
            ui,
            war_slot,
            "WAR",
            f"war_list.war.{side}",
            enabled,
            current_intent == "war",
                GAMETHEME.colors.negative,
            "Continue fighting",
        ):
            context.net_client.send_action(
                ActionOfferPeace(
                    player_id=context.net_client.player_id,
                    war_id=war_id,
                    source_country_tag=country,
                    terms="war",
                )
            )

    @staticmethod
    def _status_button(
        ui: GMLWidgets,
        slot: str,
        label: str,
        test_id: str,
        enabled: bool,
        active: bool,
        color: tuple,
        tooltip: str,
    ) -> bool:
        if active:
            imgui.push_style_color(imgui.Col_.button, (*color[:3], 0.36))
            imgui.push_style_color(imgui.Col_.button_hovered, (*color[:3], 0.56))
            imgui.push_style_color(imgui.Col_.button_active, (*color[:3], 0.76))
        try:
            return ui.button(
                slot,
                label,
                test_id,
                enabled=enabled,
                tooltip=tooltip,
            )
        finally:
            if active:
                imgui.pop_style_color(3)

    def _render_peace_page(
        self,
        state,
        war: dict[str, Any] | None,
        context: PanelRenderContext,
    ) -> None:
        with gml_child_frame(
            "War_List_Window/frmInner",
            padding=(5.0, 3.0),
            bordered=False,
        ) as visible:
            if not visible:
                return
            if war is None:
                imgui.text_disabled("Select an active war to negotiate peace.")
                return
            self._draw_coalition_summary(state, war)
            self._peace_editor.render(
                state,
                war,
                context.target_tag,
                context.is_own_country,
                context.net_client,
            )

    def _draw_status_marker(
        self,
        ui: GMLWidgets,
        slot: str,
        intent: str,
    ) -> None:
        session = active_gml_layout()
        rect = ui.rect(slot)
        if session is None or rect is None:
            return
        center = (
            session.window_position[0] + rect.x + rect.width / 2.0,
            session.window_position[1] + rect.y + rect.height / 2.0,
        )
        color = GAMETHEME.colors.positive if intent == "peace" else GAMETHEME.colors.negative
        imgui.get_window_draw_list().add_circle_filled(
            center,
            4.0,
            imgui.get_color_u32(color),
        )

    def _draw_page_icon(self, ui: GMLWidgets) -> None:
        session = active_gml_layout()
        rect = ui.rect("btnApply")
        if session is None or rect is None:
            return
        x = session.window_position[0] + rect.x
        y = session.window_position[1] + rect.y
        draw = imgui.get_window_draw_list()
        color = imgui.get_color_u32(GAMETHEME.colors.text_main)
        if self._show_peace_page:
            draw.add_line((x + 5.0, y + 8.0), (x + 12.0, y + 8.0), color, 1.0)
            draw.add_line((x + 5.0, y + 8.0), (x + 9.0, y + 5.0), color, 1.0)
            draw.add_line((x + 5.0, y + 8.0), (x + 9.0, y + 11.0), color, 1.0)
        else:
            for offset in (5.0, 8.0, 11.0):
                draw.add_line((x + 5.0, y + offset), (x + 12.0, y + offset), color, 1.0)

    def _draw_flag_at(self, x: float, y: float, tag: str) -> None:
        imgui.set_cursor_screen_pos((x, y))
        self._draw_flag(tag, 22.0, 13.0)

    def _draw_flag(self, tag: str, width: float = 20.0, height: float = 14.0) -> None:
        self._flag_renderer.draw_flag(str(tag or ""), width, height)

    def _war_exhaustion(self, state, war, country_tag: str) -> float | None:
        table = state.tables.get("war_exhaustion_states")
        if table is None or table.is_empty() or war is None:
            return None
        matches = table.filter(
            (pl.col("war_id") == str(war.get("id") or ""))
            & (
                pl.col("country_id")
                .cast(pl.Utf8)
                .str.to_uppercase()
                == str(country_tag).upper()
            )
        )
        if matches.is_empty():
            return None
        value = matches.item(0, "exhaustion_index")
        return None if value is None else float(value)

    def _draw_coalition_summary(self, state, war) -> None:
        participants = {
            self._tag(tag)
            for tag in (war.get("side_a") or []) + (war.get("side_b") or [])
        }
        table = state.tables.get("coalition_pacts")
        if table is None or table.is_empty():
            return
        coalitions = [
            row
            for row in table.to_dicts()
            if str(row.get("status") or "").lower() == "active"
            and participants.intersection(
                self._tag(tag) for tag in row.get("member_country_ids") or []
            )
        ]
        if not coalitions:
            return
        labels = [
            f"{row.get('primary_target_country_id')}: "
            f"{', '.join(row.get('member_country_ids') or [])}"
            for row in sorted(coalitions, key=lambda item: str(item.get("id") or ""))
        ]
        imgui.text_wrapped("Defensive coalitions — " + "; ".join(labels))

    @staticmethod
    def _intent(value: Any) -> str:
        return "peace" if str(value or "").strip().lower() == "peace" else "war"

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()

    @classmethod
    def _side_allies(cls, war: dict[str, Any], side_key: str, leader: str) -> list[str]:
        leader_tag = cls._tag(leader)
        return [
            tag
            for value in war.get(side_key) or []
            if (tag := cls._tag(value)) and tag != leader_tag
        ]
