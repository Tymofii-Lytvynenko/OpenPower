from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl


@dataclass(frozen=True, slots=True)
class InfrastructureCategoryView:
    category: str
    level: float
    condition: float
    capacity: float
    baseline: float
    maximum: float
    maintenance_need: float
    project_status: str = ""
    project_progress: float = 0.0
    project_reason: str = ""
    last_change_minute: int = 0
    last_source_type: str = ""
    last_source_id: str = ""
    project_id: str = ""


@dataclass(frozen=True, slots=True)
class RegionalInfrastructureView:
    region_id: int
    owner: str
    categories: tuple[InfrastructureCategoryView, ...]
    downstream_effects: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class NationalInfrastructureView:
    country_id: str
    transport_access: float
    public_service_access: float
    industrial_access: float
    telecom_access: float
    weakest_region_id: int | None
    weakest_category: str
    weakest_capacity: float


class InfrastructurePresenter:
    """Builds immutable UI projections without editing simulation state."""

    def __init__(self) -> None:
        self._region_cache: dict[tuple, RegionalInfrastructureView] = {}

    def build_region_summary(self, state: Any, region_id: int) -> RegionalInfrastructureView:
        region_id = int(region_id)
        tables = state.tables
        revisions = getattr(state, "table_revisions", None)
        cache_key = (
            region_id,
            *((int(revisions.get(name, 0)) for name in (
                "regions", "infrastructure_projects", "regional_infrastructure"
            )) if revisions is not None else (id(tables.get(name)) for name in (
                "regions", "infrastructure_projects", "regional_infrastructure"
            ))),
        )
        cached = self._region_cache.get(cache_key)
        if cached is not None:
            return cached

        regions = tables.get("regions")
        region = self._find_row(regions, "id", region_id)
        project_table = tables.get("infrastructure_projects")
        active_projects = {
            str(row.get("category") or ""): row
            for row in self._rows_for_region(project_table, region_id)
            if str(row.get("status") or "") in {"in_progress", "paused"}
        }
        profile_table = tables.get("regional_infrastructure")
        profiles = {
            str(row.get("category") or ""): row
            for row in self._rows_for_region(profile_table, region_id)
        }
        category_names = sorted(profiles)
        categories: list[InfrastructureCategoryView] = []
        for category in category_names:
            profile = profiles.get(category, {})
            level = self._ratio(profile.get("level"))
            condition = self._ratio(profile.get("condition"), 1.0)
            maintenance_level = self._ratio(profile.get("maintenance_level"))
            active_project = active_projects.get(category, {})
            categories.append(
                InfrastructureCategoryView(
                    category=category,
                    level=level,
                    condition=condition,
                    capacity=self._ratio(profile.get("capacity")),
                    baseline=self._ratio(profile.get("baseline")),
                    maximum=self._ratio(profile.get("maximum", 1.0)),
                    maintenance_need=self._ratio(profile.get("maintenance_cost_per_level_month"))
                    * level
                    * (1.0 - maintenance_level),
                    project_status=str(active_project.get("status") or ""),
                    project_id=str(active_project.get("id") or ""),
                    project_progress=self._ratio(active_project.get("progress")),
                    project_reason=str(active_project.get("reason") or ""),
                    last_change_minute=max(0, int(profile.get("last_change_minute") or 0)),
                    last_source_type=str(profile.get("last_source_type") or ""),
                    last_source_id=str(profile.get("last_source_id") or ""),
                )
            )
        effects = tuple(
            (column, self._ratio(region.get(column)))
            for column in (
                "transport_access",
                "utilities_capacity",
                "industrial_access",
                "telecom_capacity",
            )
        )
        summary = RegionalInfrastructureView(
            region_id=int(region_id),
            owner=str(region.get("owner") or ""),
            categories=tuple(categories),
            downstream_effects=effects,
        )
        self._region_cache[cache_key] = summary
        if len(self._region_cache) > 64:
            self._region_cache.pop(next(iter(self._region_cache)))
        return summary

    @staticmethod
    def _find_row(frame, key: str, value: int) -> dict[str, Any]:
        if frame is None or key not in frame.columns:
            return {}
        selected = frame.filter(pl.col(key) == value)
        return selected.row(0, named=True) if not selected.is_empty() else {}

    @staticmethod
    def _rows_for_region(frame, region_id: int) -> list[dict[str, Any]]:
        if frame is None or "region_id" not in frame.columns:
            return []
        return frame.filter(pl.col("region_id") == region_id).to_dicts()

    def build_country_summary(self, state: Any, country_tag: str) -> NationalInfrastructureView:
        country_id = str(country_tag or "").strip().upper()
        country_table = state.tables.get("countries")
        country = next(
            (
                row
                for row in ([] if country_table is None else country_table.to_dicts())
                if str(row.get("id") or "").strip().upper() == country_id
            ),
            {},
        )
        regions = state.tables.get("regions")
        owned_ids = {
            int(row.get("id") or 0)
            for row in ([] if regions is None else regions.to_dicts())
            if str(row.get("owner") or "").strip().upper() == country_id
        }
        profile_table = state.tables.get("regional_infrastructure")
        weakest = min(
            (
                row
                for row in ([] if profile_table is None else profile_table.to_dicts())
                if int(row.get("region_id") or 0) in owned_ids
            ),
            key=lambda row: (
                self._ratio(row.get("capacity")),
                int(row.get("region_id") or 0),
                str(row.get("category") or ""),
            ),
            default=None,
        )
        return NationalInfrastructureView(
            country_id=country_id,
            transport_access=self._ratio(country.get("infrastructure_index")),
            public_service_access=self._ratio(country.get("public_service_index")),
            industrial_access=self._ratio(country.get("industrial_access_index")),
            telecom_access=self._ratio(country.get("telecom_index")),
            weakest_region_id=None if weakest is None else int(weakest.get("region_id") or 0),
            weakest_category="" if weakest is None else str(weakest.get("category") or ""),
            weakest_capacity=0.0 if weakest is None else self._ratio(weakest.get("capacity")),
        )

    @staticmethod
    def _ratio(value: Any, default: float = 0.0) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            result = default
        if result != result or result in (float("inf"), float("-inf")):
            result = default
        return max(0.0, min(1.0, result))
