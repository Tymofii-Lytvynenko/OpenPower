"""REFERENCE-compatible names and ordering for shared history indicators."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_REFERENCE_HISTORY_PRESENTATION = {
    "politics.gvt_approval": (0, "Approval"),
    "politics.gvt_stability": (1, "Stability"),
    "politics.gvt_corruption": (2, "Corruption"),
    "country.overall_relations": (3, "Overall Relations"),
    "military.conventional_strength": (4, "Conventional Forces"),
    "strategic.weapon_quantity": (5, "Strategic Forces"),
    "country.expense_military_upkeep": (6, "Upkeep"),
    "research.total_level": (7, "Research"),
    "country.economic_health": (8, "Economic Health"),
    "country.gdp_per_capita": (9, "GDP per Capita"),
    "country.budget_balance": (10, "Budget"),
    "country.resource_production": (11, "Resource Production"),
    "country.resource_balance": (12, "Resource Balance"),
    "country.population": (13, "Population"),
    "country.human_dev": (14, "Human Development"),
    "country.infrastructure_index": (15, "Infrastructure"),
    "country.telecom_index": (16, "Telecom"),
}


def history_indicator_sort_key(definition: Mapping[str, Any]) -> tuple[int, int, str, str]:
    """Place available REFERENCE indicators in source order before OpenPower-only metrics."""
    indicator_id = str(definition.get("id") or "")
    source_presentation = _REFERENCE_HISTORY_PRESENTATION.get(indicator_id)
    if source_presentation is not None:
        source_index, _ = source_presentation
        return 0, source_index, "", indicator_id
    subject_type = str(definition.get("subject_type") or "country")
    return 1, 0, subject_type, indicator_id


def history_indicator_source_label(indicator_id: str) -> str | None:
    """Return the source-style label only for indicators backed by OpenPower data."""
    presentation = _REFERENCE_HISTORY_PRESENTATION.get(str(indicator_id))
    return presentation[1] if presentation is not None else None
