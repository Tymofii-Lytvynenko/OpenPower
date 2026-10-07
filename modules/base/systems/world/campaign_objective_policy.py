"""Authoritative, side-effect-free measurements used by campaign objectives."""

from __future__ import annotations

import math
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ObjectiveMeasurement:
    value: float
    available: bool
    source_table: str
    unit: str = "count"
    reason: str = ""


class ObjectiveMeasurementContext:
    """Caches authoritative table snapshots for one campaign evaluation boundary."""

    def __init__(self, state) -> None:
        self._state = state
        self._table_rows: dict[str, list[dict[str, Any]] | None] = {}
        self._measurements: dict[tuple[str, ...], ObjectiveMeasurement] = {}

    def rows(self, table_name: str) -> list[dict[str, Any]] | None:
        if table_name not in self._table_rows:
            table = self._state.tables.get(table_name)
            self._table_rows[table_name] = None if table is None else table.to_dicts()
        return self._table_rows[table_name]

    @staticmethod
    def measurement_key(objective: dict[str, Any]) -> tuple[str, ...]:
        fields = (
            "objective_type", "actor_id", "country_id", "target_id", "target_resource_id",
            "control_field", "target_ids_json", "target_branch", "weapon_type",
        )
        return tuple(str(objective.get(field) or "").strip() for field in fields)


def measure_objective(
    state,
    objective: dict[str, Any],
    context: ObjectiveMeasurementContext | None = None,
) -> ObjectiveMeasurement:
    """Reads current simulation outputs; it never reproduces a subsystem formula."""

    context = context or ObjectiveMeasurementContext(state)
    key = context.measurement_key(objective)
    cached = context._measurements.get(key)
    if cached is not None:
        return cached
    measurement = _measure_objective(state, objective, context)
    context._measurements[key] = measurement
    return measurement


def _measure_objective(
    state,
    objective: dict[str, Any],
    context: ObjectiveMeasurementContext,
) -> ObjectiveMeasurement:
    kind = _text(objective.get("objective_type")).lower()
    actor = _tag(objective.get("actor_id") or objective.get("country_id"))
    target = _text(objective.get("target_id"))
    resource = _text(objective.get("target_resource_id"))

    if kind in {"control_region", "region_control"}:
        regions = _rows(state, "regions", context)
        if regions is None or not target:
            return _missing("regions", "The target region is unavailable.")
        region = next((row for row in regions if str(row.get("id")) == target), None)
        if region is None:
            return _missing("regions", "The target region has no source record.")
        controller_column = _text(objective.get("control_field")) or "controller"
        if controller_column not in region:
            controller_column = "owner"
        if controller_column not in region:
            return _missing("regions", "The source has no owner or controller field.")
        return ObjectiveMeasurement(
            1.0 if _tag(region.get(controller_column)) == actor else 0.0,
            True,
            "regions",
            "boolean",
        )

    if kind in {"treaty_membership", "treaty_member"}:
        treaties = _rows(state, "countries_treaties", context)
        if treaties is None or not target:
            return _missing("countries_treaties", "The treaty source record is unavailable.")
        treaty = next((row for row in treaties if _text(row.get("id")) == target), None)
        if treaty is None:
            return _missing("countries_treaties", "The target treaty has no source record.")
        # Historical treaty rows remain addressable, but no longer satisfy a current membership objective.
        if _text(treaty.get("status")).lower() in {
            "cancelled", "dissolved", "expired", "inactive", "rejected", "terminated",
        }:
            return ObjectiveMeasurement(0.0, True, "countries_treaties", "boolean")
        members = _tags(treaty.get("members"))
        members |= _tags(treaty.get("side_a"))
        members |= _tags(treaty.get("side_b"))
        return ObjectiveMeasurement(1.0 if actor in members else 0.0, True, "countries_treaties", "boolean")

    if kind in {"resource_quantity", "resource_requirement", "resource"}:
        value, available, source = _resource_quantity(state, actor, resource, context)
        if not available:
            return _missing(source, "No authoritative production record exists for the requested resource.")
        return ObjectiveMeasurement(value, True, source, "units")

    if kind in {"resource_share", "resource_share_threshold"}:
        domestic = _rows(state, "domestic_production", context)
        if domestic is None or not resource:
            return _missing("domestic_production", "No resource-share source records are available.")
        matching = [row for row in domestic if _text(row.get("game_resource_id")) == resource]
        total = sum(_number(row.get("domestic_production")) for row in matching)
        if total <= 0.0:
            return _missing("domestic_production", "The resource has no positive world production total.")
        actor_total = sum(
            _number(row.get("domestic_production"))
            for row in matching
            if _tag(row.get("country_id")) == actor
        )
        return ObjectiveMeasurement(actor_total / total, True, "domestic_production", "share")

    if kind in {"gdp_per_capita", "gdp_pc"}:
        countries = _rows(state, "countries", context)
        country = next((row for row in countries or [] if _tag(row.get("id")) == actor), None)
        if country is None:
            return _missing("countries", "The objective actor has no country record.")
        explicit = country.get("gdp_per_capita")
        if explicit is not None and math.isfinite(_number(explicit, float("nan"))):
            return ObjectiveMeasurement(_number(explicit), True, "countries", "currency/person")
        gdp = _number(country.get("gdp"), float("nan"))
        population = _number(country.get("population"), float("nan"))
        if not math.isfinite(population):
            regions = _rows(state, "regions", context) or []
            brackets = ("pop_14", "pop_15_64", "pop_65")
            owned = [row for row in regions if _tag(row.get("owner")) == actor]
            if owned and all(any(field in row for field in brackets) for row in owned):
                population = sum(sum(_number(row.get(field)) for field in brackets) for row in owned)
        if not math.isfinite(gdp) or not math.isfinite(population) or population <= 0.0:
            return _missing("countries", "GDP per capita cannot be derived from complete GDP and population data.")
        return ObjectiveMeasurement(gdp / population, True, "countries", "currency/person")

    if kind in {"population", "population_threshold", "population_total"}:
        countries = _rows(state, "countries", context)
        country = next((row for row in countries or [] if _tag(row.get("id")) == actor), None)
        if country is None:
            return _missing("countries", "The objective actor has no country record.")
        population = _number(country.get("population"), float("nan"))
        if not math.isfinite(population):
            regions = _rows(state, "regions", context)
            brackets = ("pop_14", "pop_15_64", "pop_65")
            owned = [row for row in regions or [] if _tag(row.get("owner")) == actor]
            if owned and all(any(field in row for field in brackets) for row in owned):
                population = sum(sum(_number(row.get(field)) for field in brackets) for row in owned)
        if not math.isfinite(population) or population < 0.0:
            return _missing("countries", "Population cannot be derived from complete population data.")
        return ObjectiveMeasurement(population, True, "countries", "population units")

    if kind in {"development", "development_threshold", "human_development"}:
        countries = _rows(state, "countries", context)
        country = next((row for row in countries or [] if _tag(row.get("id")) == actor), None)
        if country is None:
            return _missing("countries", "The objective actor has no country record.")
        development = _number(country.get("human_dev"), float("nan"))
        if not math.isfinite(development):
            return _missing("countries", "The authoritative human-development value is unavailable.")
        return ObjectiveMeasurement(development, True, "countries", "index")

    if kind in {"conquer_country", "country_conquest"}:
        regions = _rows(state, "regions", context)
        if regions is None or not target:
            return _missing("regions", "The target country's territory data is unavailable.")
        try:
            target_region_ids = json.loads(objective.get("target_ids_json") or "[]")
        except (TypeError, ValueError):
            target_region_ids = []
        if target_region_ids:
            region_id_set = {str(value) for value in target_region_ids}
            target_regions = [row for row in regions if str(row.get("id")) in region_id_set]
        else:
            identity_fields = ("original_owner", "country_id", "homeland_country_id")
            identity_field = next((field for field in identity_fields if any(field in row for row in regions)), None)
            if identity_field:
                target_regions = [row for row in regions if _tag(row.get(identity_field)) == _tag(target)]
            else:
                target_regions = [row for row in regions if _tag(row.get("owner")) == _tag(target)]
        if not target_regions:
            return _missing("regions", "No regions are indexed to the target country; define target_region_ids for this objective.")
        owner_fields = ("controller", "owner")
        control_field = _text(objective.get("control_field")) or next(
            (field for field in owner_fields if all(field in row for row in target_regions)),
            "owner",
        )
        if any(control_field not in row for row in target_regions):
            return _missing("regions", "The target territory has no configured control field.")
        controlled = sum(_tag(row.get(control_field)) == actor for row in target_regions)
        return ObjectiveMeasurement(float(controlled), True, "regions", "regions")

    if kind in {"strategic_weapon_construction", "build_strategic_weapon", "nuclear_capability"}:
        weapons = _rows(state, "strategic_weapons", context)
        if weapons is None:
            return _missing("strategic_weapons", "Strategic weapon inventory is unavailable.")
        total = sum(
            max(0.0, _number(row.get("quantity")))
            for row in weapons
            if _tag(row.get("country_id")) == actor
            and (not target or _text(row.get("weapon_type")) == target)
        )
        return ObjectiveMeasurement(total, True, "strategic_weapons", "weapons")

    if kind in {"strategic_weapon_use", "use_strategic_weapon"}:
        orders = _rows(state, "strategic_launch_orders", context)
        if orders is None:
            return _missing("strategic_launch_orders", "Strategic launch history is unavailable.")
        used = sum(
            1
            for row in orders
            if _tag(row.get("country_id")) == actor
            and str(row.get("status") or "").lower() not in {"rejected", "cancelled"}
            and (not target or _text(row.get("weapon_type")) == target)
        )
        return ObjectiveMeasurement(float(used), True, "strategic_launch_orders", "launches")

    if kind in {"research_level", "research"}:
        tracks = _rows(state, "research_tracks", context)
        if tracks is None:
            return _missing("research_tracks", "Research tracks are unavailable.")
        branch = _text(objective.get("target_branch")) or target
        matching = [
            row for row in tracks
            if _tag(row.get("country_id")) == actor
            and (not branch or _text(row.get("branch")) == branch)
        ]
        if not matching:
            return _missing("research_tracks", "No matching research track exists for this actor.")
        return ObjectiveMeasurement(
            max(_number(row.get("research_level", row.get("progress"))) for row in matching),
            True,
            "research_tracks",
            "level",
        )

    return _missing("", f"Unsupported objective type '{kind}'.")


def _resource_quantity(
    state,
    actor: str,
    resource: str,
    context: ObjectiveMeasurementContext | None = None,
) -> tuple[float, bool, str]:
    table = _rows(state, "domestic_production", context)
    source = "domestic_production"
    if not resource:
        return 0.0, False, source
    matches = [] if table is None else [
        row for row in table
        if _tag(row.get("country_id")) == actor
        and _text(row.get("game_resource_id")) == resource
    ]
    if not matches and source == "domestic_production":
        regional = _rows(state, "regional_production", context)
        if regional is not None:
            matches = [
                row for row in regional
                if _tag(row.get("country_id")) == actor
                and _text(row.get("game_resource_id")) == resource
            ]
            source = "regional_production"
    if not matches:
        return 0.0, False, source
    return sum(_number(row.get("domestic_production")) for row in matches), True, source


def _rows(
    state,
    table_name: str,
    context: ObjectiveMeasurementContext | None = None,
) -> list[dict[str, Any]] | None:
    if context is not None:
        return context.rows(table_name)
    table = state.tables.get(table_name)
    if table is None:
        return None
    return table.to_dicts()


def _missing(source: str, reason: str) -> ObjectiveMeasurement:
    return ObjectiveMeasurement(0.0, False, source, reason=reason)


def _tag(value: Any) -> str:
    return _text(value).upper()


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _tags(value: Any) -> set[str]:
    if isinstance(value, str):
        values = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = []
    return {_tag(item) for item in values if _tag(item)}


def _number(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return result if math.isfinite(result) else fallback
