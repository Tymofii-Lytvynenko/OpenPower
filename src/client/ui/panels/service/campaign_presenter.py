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
        campaigns = self._rows(state, "campaigns")
        owned = [
            row for row in campaigns
            if str(row.get("actor_country_id") or "").strip().upper() == actor
        ]
        owned.sort(
            key=lambda row: (
                int(row.get("started_at_minute") or 0),
                str(row.get("id") or ""),
            ),
            reverse=True,
        )
        campaign = owned[0] if owned else None
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
    def _rows(state, table_name: str) -> list[dict[str, Any]]:
        table = getattr(state, "tables", {}).get(table_name)
        return [] if table is None or table.is_empty() else table.to_dicts()
