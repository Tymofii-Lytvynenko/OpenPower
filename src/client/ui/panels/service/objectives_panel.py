from __future__ import annotations

import json

from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.service.campaign_presenter import CampaignPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state
from src.shared.actions import ActionSetSphereDelegation


class ObjectivesPanel:
    def __init__(self):
        self._presenter = CampaignPresenter()
        self._selected_sphere_id = ""

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("OBJECTIVES", x=980, y=120, w=520, h=430) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        country_tag = context.target_tag
        overview = self._presenter.build_overview(state, country_tag)
        campaign = overview.campaign
        if campaign:
            scenario = overview.scenario or {}
            title = str(scenario.get("title") or campaign.get("scenario_id") or "Campaign")
            imgui.text_colored(GAMETHEME.colors.accent, title)
            outcome = str(campaign.get("outcome") or "ongoing").replace("_", " ").title()
            Prims.right_align_text(outcome, GAMETHEME.colors.positive if outcome in {"Victory", "Sandbox"} else GAMETHEME.colors.info)
            if campaign.get("outcome_reason"):
                imgui.text_wrapped(str(campaign["outcome_reason"]))
            if campaign.get("sandbox_continuation"):
                imgui.text_disabled("You may continue playing after the scenario outcome.")

        objectives = overview.objectives
        if not objectives:
            draw_empty_state("No objectives are assigned. This campaign remains an open sandbox.")
        else:
            for row in objectives:
                self._render_objective(row, int(state.time.total_minutes))

        if overview.recommendations:
            imgui.separator()
            imgui.text_colored(GAMETHEME.colors.accent, "Advisor priorities")
            for item in overview.recommendations[:5]:
                urgency = max(0, min(100, int(float(item.get("urgency") or 0.0) * 100)))
                imgui.text(f"{urgency}%  {item.get('title') or 'Recommendation'}")
                imgui.push_text_wrap_pos(0.0)
                imgui.text_colored(GAMETHEME.colors.text_dim, str(item.get("reason") or ""))
                imgui.pop_text_wrap_pos()
                imgui.text_disabled(f"Expires in {max(0, int(item.get('expires_at_minute') or 0) - int(state.time.total_minutes)) // 1440} day(s)")

        if campaign and context.is_own_country and context.net_client is not None:
            self._render_delegation_controls(state, context, overview.delegations, country_tag)

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

    @staticmethod
    def _render_objective(row: dict, now: int) -> None:
        title = str(row.get("title") or "Objective")
        description = str(row.get("description") or "")
        status = str(row.get("status") or "pending").upper()
        progress = max(0.0, min(100.0, float(row.get("progress") or 0.0) * 100.0))
        color = GAMETHEME.colors.positive if status == "COMPLETED" else GAMETHEME.colors.info

        imgui.text_colored(GAMETHEME.colors.text_main, title)
        imgui.same_line()
        Prims.right_align_text(status, color)
        if description:
            imgui.push_text_wrap_pos(0.0)
            imgui.text_colored(GAMETHEME.colors.text_dim, description)
            imgui.pop_text_wrap_pos()
        current = float(row.get("current_value") or 0.0)
        target = float(row.get("target_value") or 0.0)
        remaining = float(row.get("remaining") or 0.0)
        if row.get("objective_type"):
            imgui.text_disabled(f"Current {current:,.2f} / target {target:,.2f}; remaining {remaining:,.2f}")
        deadline = int(row.get("deadline_at_minute", -1))
        if deadline >= 0:
            imgui.text_disabled(f"Deadline: {max(0, deadline - now) // 1440} day(s) remaining")
        if int(row.get("hold_duration_minutes") or 0) > 0:
            imgui.text_disabled(
                f"Held {int(row.get('held_minutes') or 0)} / {int(row.get('hold_duration_minutes') or 0)} minute(s)"
            )
        if status == "BLOCKED":
            imgui.text_colored(GAMETHEME.colors.warning, str(row.get("missing_data_reason") or row.get("reason") or "Required data is missing."))
        elif row.get("reason"):
            imgui.text_disabled(str(row.get("reason")))
        evidence = CampaignPresenter.latest_evidence(row)
        if evidence:
            source = str(evidence.get("source_table") or "campaign state")
            minute = int(evidence.get("game_minute") or 0)
            imgui.text_disabled(
                f"Latest evidence: {source} at minute {minute} "
                f"({float(evidence.get('current_value') or 0.0):,.2f} / "
                f"{float(evidence.get('target_value') or 0.0):,.2f})"
            )
        Prims.meter("", progress, color)
        imgui.dummy((0.0, 6.0))
