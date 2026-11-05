from __future__ import annotations

import json

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import get_gml_layout
from src.client.ui.panels.service.campaign_presenter import CampaignPresenter
from src.client.ui.panels.service.objectives_window_content import (
    ObjectivesWindowContent,
)
from src.client.ui.panels.shared.panel_widgets import draw_empty_state
from src.shared.actions import (
    ActionResolveAdvisorRecommendation,
    ActionSetSphereDelegation,
)


class ObjectivesPanel:
    def __init__(self):
        self._presenter = CampaignPresenter()
        self._selected_sphere_id = ""
        self._window_content = ObjectivesWindowContent()

    def render(self, state, context: PanelRenderContext) -> bool:
        layout = get_gml_layout("Objectives_Window")
        viewport = imgui.get_main_viewport().size
        x = min(980.0, max(0.0, float(viewport.x) - layout.width - 10.0))
        y = min(120.0, max(0.0, float(viewport.y) - layout.height - 112.0))
        with WindowManager.window(
            "OBJECTIVES", x=x, y=y, w=layout.width, h=layout.height,
            test_id="objectives.panel", gml_template="Objectives_Window",
            avoid_overlaps=True, placement_margin=10.0, bottom_clearance=112.0,
        ) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        country_tag = context.target_tag
        overview = self._presenter.build_overview(state, country_tag)
        now = int(state.time.total_minutes)
        self._window_content.render(
            overview,
            country_tag,
            now,
            render_openpower_advice=lambda: self._render_advice_controls(
                state, context, overview, country_tag, now,
            ),
        )

    def _render_advice_controls(self, state, context, overview, country_tag: str, now: int) -> None:
        if overview.recommendations:
            imgui.separator()
            imgui.text_colored(GAMETHEME.colors.accent, "OpenPower advisor recommendations")
            self._render_recommendations(context, overview.recommendations, country_tag, now)
        if overview.campaign and context.is_own_country and context.net_client is not None:
            self._render_delegation_controls(
                state, context, list(overview.delegations), country_tag,
            )
        if not overview.recommendations and not overview.delegations:
            draw_empty_state("No advisor recommendations or delegated scopes are available.")

    def _render_recommendations(self, context, recommendations, country_tag: str, now: int) -> None:
        visible_recommendations = recommendations[:5]
        for index, item in enumerate(visible_recommendations):
            source_signal = str(item.get("source_signal") or "")
            is_policy = source_signal.startswith("ai_policy:")
            urgency = max(0, min(100, int(float(item.get("urgency") or 0.0) * 100)))
            title = str(item.get("title") or "Recommendation")
            title_line = f"{'AI PROPOSAL' if is_policy else f'{urgency}%'}  {title}"
            visible_title = Prims.fit_text(title_line, 255.0)
            imgui.text(visible_title)
            if visible_title != title_line and imgui.is_item_hovered():
                imgui.set_tooltip(title_line)
            reason = str(item.get("reason") or "")
            visible_reason = Prims.fit_text(reason, 255.0)
            imgui.text_colored(GAMETHEME.colors.text_dim, visible_reason)
            if visible_reason != reason and imgui.is_item_hovered():
                imgui.set_tooltip(reason)
            expires_in = max(
                0,
                int(item.get("expires_at_minute") or 0)
                - now,
            ) // 1440
            imgui.text_disabled(f"Expires in {expires_in} day(s)")
            imgui.same_line()
            recommendation_id = str(item.get("id") or "")
            action_label = self._presenter.recommendation_action_label(item)
            review_callback = context.on_advisor_recommendation
            if (
                context.is_own_country
                and action_label
                and (review_callback is not None or context.on_question is not None)
                and context.net_client is not None
            ):
                if imgui.small_button(
                    f"Review##{recommendation_id}",
                    test_id=f"objectives.recommendation.review.{recommendation_id}",
                ):
                    if review_callback is not None:
                        review_callback(item)
                    else:
                        self._open_recommendation_question(context, country_tag, item, action_label)
            elif context.is_own_country and context.on_notice is not None and context.net_client is not None:
                if imgui.small_button(
                    f"Read##{recommendation_id}",
                    test_id=f"objectives.recommendation.read.{recommendation_id}",
                ):
                    context.on_notice(
                        title,
                        str(item.get("reason") or ""),
                        on_acknowledge=lambda item_id=recommendation_id: self._resolve_recommendation(
                            context, country_tag, item_id, accept=False,
                        ),
                    )
            if index + 1 < len(visible_recommendations):
                imgui.separator()

    def _open_recommendation_question(self, context, country_tag: str, item: dict, action_label: str) -> None:
        if context.on_question is None:
            return
        title = str(item.get("title") or "Advisor recommendation")
        reason = str(item.get("reason") or "")
        message = f"{title}\n\n{reason}\n\nSuggested action: {action_label}. Apply it?"
        recommendation_id = str(item.get("id") or "")
        context.on_question(
            message,
            lambda: self._resolve_recommendation(context, country_tag, recommendation_id, accept=True),
            lambda: self._resolve_recommendation(context, country_tag, recommendation_id, accept=False),
        )

    @staticmethod
    def _resolve_recommendation(context, country_tag: str, recommendation_id: str, *, accept: bool) -> None:
        client = context.net_client
        if client is None:
            return
        client.send_action(ActionResolveAdvisorRecommendation(
            player_id=client.player_id,
            recommendation_id=recommendation_id,
            accept=accept,
        ))

    def _render_delegation_controls(self, state, context, delegations: list[dict], country_tag: str) -> None:
        country = str(country_tag or "").strip().upper()
        active = [
            row for row in delegations
            if str(row.get("owner_country_id") or "").strip().upper() == country and bool(row.get("active"))
        ]
        imgui.separator()
        imgui.text_colored(GAMETHEME.colors.accent, "Delegated scopes")
        for row in active:
            scope_type = str(row.get("scope_type") or "country")
            scope_id = str(row.get("scope_id") or country)
            authority = self._json_values(row.get("authority_json"))
            imgui.text(self._delegation_summary(row))
            if imgui.button(f"Return {scope_type} control##{scope_type}:{scope_id}"):
                context.net_client.send_action(ActionSetSphereDelegation(
                    player_id=context.net_client.player_id,
                    country_tag=country,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    delegate_id=str(row.get("delegate_id") or "ai"),
                    authority=authority,
                    priorities=self._json_values(row.get("priorities_json")),
                    active=False,
                    return_condition=str(row.get("return_condition") or "manual"),
                ))

        occupied = {(str(row.get("scope_type") or ""), str(row.get("scope_id") or "")) for row in active}
        if ("country", country) not in occupied:
            if imgui.button("Delegate economic policy to AI"):
                self._send_delegation(context, country, "country", country, ["economy"], ["campaign_objectives"])

        ruling_party = self._ruling_party_id(state, country)
        if ruling_party and ("party", ruling_party) not in occupied:
            if imgui.button("Delegate ruling-party politics to AI"):
                self._send_delegation(context, country, "party", ruling_party, ["politics"], ["campaign_politics"])

        spheres = self._active_treaty_scopes(state, country)
        if spheres:
            if self._selected_sphere_id not in spheres:
                self._selected_sphere_id = spheres[0]
            preview = self._selected_sphere_id
            if imgui.begin_combo("Treaty sphere", preview):
                for treaty_id in spheres:
                    if imgui.selectable(treaty_id, treaty_id == self._selected_sphere_id)[0]:
                        self._selected_sphere_id = treaty_id
                imgui.end_combo()
            if ("sphere", self._selected_sphere_id) not in occupied and imgui.button("Delegate treaty diplomacy to AI"):
                self._send_delegation(
                    context, country, "sphere", self._selected_sphere_id, ["diplomacy"], ["treaty_membership"],
                )

    @staticmethod
    def _send_delegation(context, country: str, scope_type: str, scope_id: str, authority: list[str], priorities: list[str]) -> None:
        context.net_client.send_action(ActionSetSphereDelegation(
            player_id=context.net_client.player_id,
            country_tag=country,
            scope_type=scope_type,
            scope_id=scope_id,
            delegate_id="ai",
            authority=authority,
            priorities=priorities,
            active=True,
        ))

    @staticmethod
    def _json_values(value) -> list[str]:
        try:
            parsed = json.loads(value or "[]") if isinstance(value, str) else value
        except (TypeError, ValueError):
            return []
        if not isinstance(parsed, (list, tuple, set)):
            return []
        return [str(item) for item in parsed if str(item)]

    @staticmethod
    def _delegation_summary(row: dict) -> str:
        scope_type = str(row.get("scope_type") or "country").title()
        scope_id = str(row.get("scope_id") or "")
        authority = ", ".join(ObjectivesPanel._json_values(row.get("authority_json"))) or "none"
        priorities = ", ".join(ObjectivesPanel._json_values(row.get("priorities_json"))) or "none"
        return_condition = str(row.get("return_condition") or "manual").replace("_", " ")
        return (
            f"{scope_type} · {scope_id} · AI authority: {authority} · "
            f"priorities: {priorities} · return: {return_condition}"
        )

    @staticmethod
    def _ruling_party_id(state, country: str) -> str:
        governments = state.tables.get("country_governments")
        if governments is not None and {"country_id", "ruling_party_id"}.issubset(governments.columns):
            row = next((row for row in governments.to_dicts() if str(row.get("country_id") or "").upper() == country), None)
            if row and row.get("ruling_party_id"):
                return str(row["ruling_party_id"])
        parties = state.tables.get("political_parties")
        if parties is not None and {"country_id", "party_id", "is_ruling"}.issubset(parties.columns):
            row = next((row for row in parties.to_dicts() if str(row.get("country_id") or "").upper() == country and bool(row.get("is_ruling"))), None)
            return str(row.get("party_id") or "") if row else ""
        return ""

    @staticmethod
    def _active_treaty_scopes(state, country: str) -> list[str]:
        treaties = state.tables.get("countries_treaties")
        if treaties is None or not {"id", "members"}.issubset(treaties.columns):
            return []
        result = []
        for row in treaties.to_dicts():
            if str(row.get("status") or "active").lower() != "active":
                continue
            members = row.get("members") or []
            if isinstance(members, str):
                try:
                    members = json.loads(members)
                except (TypeError, ValueError):
                    members = []
            if isinstance(members, (list, tuple, set)) and country in {str(item).upper() for item in members}:
                result.append(str(row.get("id") or ""))
        return sorted(item for item in result if item)
