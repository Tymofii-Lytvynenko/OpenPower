from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


@dataclass(frozen=True, slots=True)
class CampaignOverview:
    campaign: dict[str, Any] | None
    scenario: dict[str, Any] | None
    objectives: tuple[dict[str, Any], ...]
    recommendations: tuple[dict[str, Any], ...]
    delegations: tuple[dict[str, Any], ...]


class CampaignPresenter:
    """Projects persistent campaign records into a country-scoped UI model."""

    def build_overview(self, state, country_tag: str) -> CampaignOverview:
        actor = str(country_tag or "").strip().upper()
        campaign = self.latest_campaign(state, actor)
        scenario = None
        campaign_id = str(campaign.get("id") or "") if campaign else ""
        if campaign:
            scenario = next(
                (
                    row for row in self._rows(state, "campaign_scenarios")
                    if str(row.get("id") or "") == str(campaign.get("scenario_id") or "")
                ),
                None,
            )

        objectives = [
            row for row in self._rows(state, "objectives")
            if (
                str(row.get("campaign_id") or "") == campaign_id
                if campaign_id
                else str(row.get("country_id") or "").strip().upper() == actor
            )
        ]
        objectives.sort(
            key=lambda row: (
                str(row.get("status") or "active") in {"completed", "failed", "expired", "cancelled"},
                int(row.get("deadline_at_minute") or (1 << 60)),
                -float(row.get("progress") or 0.0),
                str(row.get("id") or ""),
            )
        )
        recommendations = [
            row for row in self._rows(state, "advisor_recommendations")
            if str(row.get("actor_country_id") or "").strip().upper() == actor
            and str(row.get("status") or "active") == "active"
        ]
        recommendations.sort(
            key=lambda row: (
                -float(row.get("urgency") or 0.0),
                int(row.get("expires_at_minute") or 0),
                str(row.get("id") or ""),
            )
        )
        delegations = [
            row for row in self._rows(state, "sphere_delegations")
            if str(row.get("owner_country_id") or "").strip().upper() == actor
            and (not campaign_id or str(row.get("campaign_id") or "") == campaign_id)
        ]
        delegations.sort(key=lambda row: (str(row.get("scope_type") or ""), str(row.get("scope_id") or "")))
        return CampaignOverview(
            campaign=campaign,
            scenario=scenario,
            objectives=tuple(objectives),
            recommendations=tuple(recommendations),
            delegations=tuple(delegations),
        )

    def latest_campaign(self, state, country_tag: str) -> dict[str, Any] | None:
        """Return the current campaign using the same ordering as the overview."""
        actor = str(country_tag or "").strip().upper()
        owned = [
            row for row in self._rows(state, "campaigns")
            if str(row.get("actor_country_id") or "").strip().upper() == actor
        ]
        owned.sort(
            key=lambda row: (
                int(row.get("started_at_minute") or 0),
                str(row.get("id") or ""),
            ),
            reverse=True,
        )
        return owned[0] if owned else None

    @staticmethod
    def latest_evidence(objective: dict[str, Any]) -> dict[str, Any] | None:
        evidence = objective.get("evidence_json") or []
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except (TypeError, ValueError, json.JSONDecodeError):
                return None
        if not isinstance(evidence, list) or not evidence or not isinstance(evidence[-1], dict):
            return None
        return evidence[-1]

    @staticmethod
    def recommendation_action_label(recommendation: dict[str, Any]) -> str:
        """Describe only the action payload that the authoritative resolver can execute."""
        payload = CampaignPresenter._recommendation_payload(recommendation)
        if payload is None:
            return ""
        action_type = payload[0]
        fields = payload[1]
        if action_type == "ActionUpdateBudget":
            return "update budget allocations"
        if action_type == "ActionChangeEconomicPolicy":
            return f"change {str(fields.get('policy_name') or 'economic policy').replace('_', ' ')}"
        if action_type == "ActionRequestDebtContract":
            return "request a debt contract"
        if action_type == "ActionResolveDebtContract":
            return "accept a debt contract"
        if action_type == "ActionChangePoliticalLaw":
            return f"change {str(fields.get('law_id') or 'a political law').replace('_', ' ')}"
        if action_type == "ActionSetElectionOverride":
            return "set an election override"
        if action_type == "ActionResolvePoliticalCrisis":
            return "resolve a political crisis"
        if action_type == "ActionBuildUnit":
            return f"build {int(fields.get('count') or 0)} {str(fields.get('unit_type') or 'unit')}(s)"
        if action_type == "ActionQueueUnitProduction":
            return "queue unit production"
        if action_type == "ActionBuyMarketUnit":
            return "buy a listed unit"
        if action_type == "ActionTrainUnit":
            return f"train unit to {str(fields.get('target_level') or 'the selected level')}"
        return ""

    @staticmethod
    def _recommendation_payload(recommendation: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
        raw = recommendation.get("optional_action_json")
        if not isinstance(raw, str) or not raw.strip():
            return None
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("fields"), dict):
            return None
        return str(payload.get("type") or ""), payload["fields"]

    @staticmethod
    def _rows(state, table_name: str) -> list[dict[str, Any]]:
        table = getattr(state, "tables", {}).get(table_name)
        return [] if table is None or table.is_empty() else table.to_dicts()
