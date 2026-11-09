"""Shared interpretation of current regional control for UI and authority checks."""

from __future__ import annotations

from typing import Any


# _tag normalizes occupation statuses to uppercase before this filter runs.
_INACTIVE_OCCUPATION_STATUSES = frozenset({"ENDED", "CANCELLED", "INACTIVE"})


def region_controlled_by_country(state: Any, region: dict[str, Any], country_id: str) -> bool:
    country = _tag(country_id)
    controller = _tag(region.get("controller"))
    if controller:
        return controller == country

    occupations = getattr(state, "tables", {}).get("occupations")
    if occupations is not None and {"region_id", "controller_country_id"}.issubset(occupations.columns):
        region_id = _integer(region.get("id"))
        for occupation in occupations.iter_rows(named=True):
            if (
                _integer(occupation.get("region_id")) == region_id
                and _tag(occupation.get("controller_country_id")) == country
                and _tag(occupation.get("occupation_status")) not in _INACTIVE_OCCUPATION_STATUSES
            ):
                return True
    return _tag(region.get("owner")) == country


def country_region_control_proportion(
    state: Any,
    controller_country_id: str,
    political_country_id: str,
) -> float | None:
    """Return the share of a country's political regions held by a controller."""

    controller = _tag(controller_country_id)
    political_country = _tag(political_country_id)
    regions = getattr(state, "tables", {}).get("regions")
    if (
        not controller
        or not political_country
        or controller == political_country
        or regions is None
        or not {"id", "owner"}.issubset(regions.columns)
    ):
        return None

    active_occupations: set[int] = set()
    occupations = getattr(state, "tables", {}).get("occupations")
    if occupations is not None and {
        "region_id", "controller_country_id"
    }.issubset(occupations.columns):
        for occupation in occupations.iter_rows(named=True):
            if (
                _tag(occupation.get("controller_country_id")) == controller
                and _tag(occupation.get("occupation_status"))
                not in _INACTIVE_OCCUPATION_STATUSES
            ):
                active_occupations.add(_integer(occupation.get("region_id")))

    total = controlled = 0
    has_controller = "controller" in regions.columns
    for region in regions.iter_rows(named=True):
        if _tag(region.get("owner")) != political_country:
            continue
        total += 1
        military_controller = _tag(region.get("controller")) if has_controller else ""
        if military_controller:
            controlled += military_controller == controller
        else:
            region_id = _integer(region.get("id"))
            controlled += region_id in active_occupations
            if region_id not in active_occupations:
                controlled += political_country == controller

    return controlled / total if total else None


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
