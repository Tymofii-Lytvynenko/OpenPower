from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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

    def build_region_summary(self, state: Any, region_id: int) -> RegionalInfrastructureView:
        regions = state.tables.get("regions")
        region = next(
            (
                row
                for row in ([] if regions is None else regions.to_dicts())
                if int(row.get("id") or 0) == int(region_id)
            ),
            {},
        )
        project_table = state.tables.get("infrastructure_projects")
        active_projects = {
            str(row.get("category") or ""): row
            for row in ([] if project_table is None else project_table.to_dicts())
            if int(row.get("region_id") or 0) == int(region_id)
            and str(row.get("status") or "") in {"in_progress", "paused"}
        }
        profile_table = state.tables.get("regional_infrastructure")
        profiles = {
            str(row.get("category") or ""): row
            for row in ([] if profile_table is None else profile_table.to_dicts())
            if int(row.get("region_id") or 0) == int(region_id)
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
        return RegionalInfrastructureView(
            region_id=int(region_id),
            owner=str(region.get("owner") or ""),
            categories=tuple(categories),
            downstream_effects=effects,
        )

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
