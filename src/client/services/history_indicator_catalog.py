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
_HISTORICAL_BASELINE_PRESENTATION = {
    "country.baseline_2001.birth_rate": (17, "Birth Rate (2001)"),
    "country.baseline_2001.death_rate": (18, "Death Rate (2001)"),
    "country.baseline_2001.fertility_rate": (19, "Fertility Rate (2001)"),
    "country.baseline_2001.life_expectancy": (20, "Life Expectancy (2001)"),
    "country.baseline_2001.arable_land_pct": (21, "Arable Land (2001)"),
    "country.baseline_2001.forest_area_pct": (22, "Forest Area (2001)"),
    "country.baseline_2001.land_area": (23, "Land Area (2001)"),
    "country.baseline_2001.total_surface_area": (24, "Total Surface Area (2001)"),
    "country.baseline_2001.inland_water_area": (25, "Inland Water Area (2001)"),
    "country.baseline_2001.national_park_area": (26, "National Park Area (2001)"),
    "country.baseline_2001.national_park_land_coverage": (27, "National Park Land Coverage (2001)"),
    "country.baseline_2001.other_land_pct": (28, "Other Land (2001)"),
    "country.baseline_2001.human_development": (29, "Human Development (2001)"),
    "country.baseline_2001.undp_life_expectancy": (30, "UNDP Life Expectancy (2001)"),
    "country.baseline_2001.expected_years_schooling": (31, "Expected Schooling (2001)"),
    "country.baseline_2001.mean_years_schooling": (32, "Mean Schooling (2001)"),
    "country.baseline_2001.gni_per_capita_ppp": (33, "GNI per Capita (2001)"),
    "country.baseline_2000.protected_area_pct": (34, "Protected Areas (2000)"),
    "country.historical_poverty_line_estimate": (35, "Historical Poverty-Line Estimate"),
}


def history_indicator_sort_key(definition: Mapping[str, Any]) -> tuple[int, int, str, str]:
    """Place available REFERENCE indicators in source order before OpenPower-only metrics."""
    indicator_id = str(definition.get("id") or "")
    source_presentation = _REFERENCE_HISTORY_PRESENTATION.get(indicator_id)
    if source_presentation is not None:
        source_index, _ = source_presentation
        return 0, source_index, "", indicator_id
    historical_presentation = _HISTORICAL_BASELINE_PRESENTATION.get(indicator_id)
    if historical_presentation is not None:
        source_index, _ = historical_presentation
        return 0, source_index, "", indicator_id
    subject_type = str(definition.get("subject_type") or "country")
    return 1, 0, subject_type, indicator_id


def history_indicator_source_label(indicator_id: str) -> str | None:
    """Return the source-style label only for indicators backed by OpenPower data."""
    presentation = _REFERENCE_HISTORY_PRESENTATION.get(str(indicator_id))
    if presentation is None:
        presentation = _HISTORICAL_BASELINE_PRESENTATION.get(str(indicator_id))
    return presentation[1] if presentation is not None else None
