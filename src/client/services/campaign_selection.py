from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

import polars as pl


@dataclass(frozen=True, slots=True)
class ObjectivePreview:
    title: str
    deadline: str


@dataclass(frozen=True, slots=True)
class CampaignScenarioPreview:
    scope: str
    enabled_rules: tuple[str, ...]
    objectives: tuple[ObjectivePreview, ...]
    max_duration_minutes: int


def filter_selectable_countries(
    playable_countries: pl.DataFrame,
    scenario: Mapping[str, Any] | None,
) -> pl.DataFrame:
    """Filters the new-game actor list using the selected scenario's allowlist."""
    if playable_countries.is_empty() or "id" not in playable_countries.columns or scenario is None:
        return playable_countries
    try:
        selectable = _json_list(scenario.get("selectable_country_ids_json", "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return playable_countries.head(0)
    if not selectable:
        return playable_countries
    allowed = sorted({str(value).strip().upper() for value in selectable if str(value).strip()})
    if not allowed:
        return playable_countries.head(0)
    return playable_countries.filter(
        pl.col("id").cast(pl.Utf8).str.to_uppercase().is_in(allowed)
    )


def preview_campaign_scenario(scenario: Mapping[str, Any] | None) -> CampaignScenarioPreview:
    if scenario is None:
        return CampaignScenarioPreview("Country", (), (), 0)
    political_scope = str(scenario.get("political_scope") or "country").strip().replace("_", " ").title()
    sphere_scope = str(scenario.get("sphere_scope") or "").strip()
    scope = f"{political_scope}: {sphere_scope}" if sphere_scope else political_scope
    try:
        rules = _json_object(scenario.get("enabled_rules_json", "{}"))
        objectives = _json_list(scenario.get("objectives_json", "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        rules, objectives = {}, []
    enabled_rules = tuple(sorted(str(key) for key, enabled in rules.items() if bool(enabled)))
    previews = tuple(
        ObjectivePreview(
            title=str(item.get("title") or item.get("id") or "Campaign objective"),
            deadline=_deadline_label(item),
        )
        for item in objectives
        if isinstance(item, dict)
    )
    try:
        max_duration = max(0, int(scenario.get("max_duration_minutes") or 0))
    except (TypeError, ValueError, OverflowError):
        max_duration = 0
    return CampaignScenarioPreview(scope, enabled_rules, previews, max_duration)


def _deadline_label(objective: Mapping[str, Any]) -> str:
    absolute = objective.get("deadline_at_minute")
    if absolute is not None:
        try:
            minute = int(absolute)
        except (TypeError, ValueError, OverflowError):
            minute = -1
        if minute >= 0:
            return f"game minute {minute}"
    relative = objective.get("deadline_minutes")
    if relative is not None:
        try:
            minutes = max(0, int(relative))
        except (TypeError, ValueError, OverflowError):
            minutes = 0
        return f"within {minutes} minute(s)"
    return "no deadline"


def _json_list(value: Any) -> list[Any]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON list.")
    return parsed


def _json_object(value: Any) -> dict[str, Any]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object.")
    return parsed
