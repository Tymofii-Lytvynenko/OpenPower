"""Complete ready production orders and publish their new deployment groups."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import polars as pl

from modules.base.systems.military.deployment_service import DeploymentOrderSpec
from modules.base.systems.military.home_region_policy import MilitaryHomeRegionPolicy
from modules.base.systems.military.movement_duration import MovementDurationPolicy
from modules.base.systems.military.unit_factory import (
    DEFAULT_UNIT_TYPE,
    UnitRecordSpec,
)
from modules.base.systems.world.demilitarization_policy import DemilitarizationPolicy
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


class _UnitFactory(Protocol):
    def next_id(
        self,
        unit_rows: list[dict[str, Any]],
        country_tag: str,
        unit_type: str,
    ) -> str: ...

    def create_from_spec(self, spec: UnitRecordSpec) -> dict[str, Any]: ...


class _DeploymentOrderCreator(Protocol):
    def create_order_record(
        self,
        spec: DeploymentOrderSpec,
        existing_deployments: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class _EligibleProductionOrder:
    country_tag: str
    country: dict[str, Any]
    design: dict[str, Any]
    quantity: int


@dataclass
class _ProductionCompletionBatch:
    state: GameState
    countries: pl.DataFrame
    orders_table: pl.DataFrame
    country_rows: list[dict[str, Any]]
    order_rows: list[dict[str, Any]]
    unit_rows: list[dict[str, Any]]
    deployments_table: pl.DataFrame | None
    deployment_rows: list[dict[str, Any]]
    countries_by_tag: dict[str, dict[str, Any]]
    designs_by_id: dict[str, dict[str, Any]]
    home_regions: dict[str, int]
    region_locations: dict[int, GeoCoordinate]
    changed: bool = False


class MilitaryProductionCompletionService:
    """Apply production completion policy and create off-map deployment groups."""

    def __init__(
        self,
        unit_factory: _UnitFactory,
        demilitarization_policy: DemilitarizationPolicy,
        duration_policy: MovementDurationPolicy,
        deployment_order_creator: _DeploymentOrderCreator,
        home_region_policy: MilitaryHomeRegionPolicy,
        ensure_country_columns: Callable[[pl.DataFrame], pl.DataFrame],
        units_from_rows: Callable[[list[dict[str, Any]]], pl.DataFrame],
    ) -> None:
        self._unit_factory = unit_factory
        self._demilitarization_policy = demilitarization_policy
        self._duration_policy = duration_policy
        self._deployment_order_creator = deployment_order_creator
        self._home_region_policy = home_region_policy
        self._ensure_country_columns = ensure_country_columns
        self._units_from_rows = units_from_rows

    def process_completed_orders(
        self,
        state: GameState,
        units: pl.DataFrame,
    ) -> pl.DataFrame:
        batch = self._create_batch(state, units)
        if batch is None:
            return units

        for order in batch.order_rows:
            self._process_order(order, batch)
        if not batch.changed:
            return units

        state.update_table(
            "countries",
            pl.DataFrame(batch.country_rows, schema=batch.countries.schema),
        )
        state.update_table(
            "production_orders",
            pl.DataFrame(batch.order_rows, schema=batch.orders_table.schema),
        )
        if batch.deployments_table is not None:
            state.update_table(
                "unit_deployment_orders",
                pl.DataFrame(
                    batch.deployment_rows,
                    schema=batch.deployments_table.schema,
                ),
            )
        return self._units_from_rows(batch.unit_rows)

    def _create_batch(
        self,
        state: GameState,
        units: pl.DataFrame,
    ) -> _ProductionCompletionBatch | None:
        required_tables = {"countries", "regions", "unit_designs", "production_orders"}
        if not required_tables.issubset(state.tables):
            return None

        orders_table = state.get_table("production_orders")
        if orders_table.is_empty():
            return None

        countries = self._ensure_country_columns(state.get_table("countries"))
        regions = state.get_table("regions")
        country_rows = countries.to_dicts()
        return _ProductionCompletionBatch(
            state=state,
            countries=countries,
            orders_table=orders_table,
            country_rows=country_rows,
            order_rows=orders_table.to_dicts(),
            unit_rows=units.to_dicts(),
            deployments_table=state.tables.get("unit_deployment_orders"),
            deployment_rows=(
                []
                if state.tables.get("unit_deployment_orders") is None
                else state.tables["unit_deployment_orders"].to_dicts()
            ),
            countries_by_tag={
                str(row.get("id") or "").strip().upper(): row
                for row in country_rows
            },
            designs_by_id={
                str(row.get("id") or ""): row
                for row in state.get_table("unit_designs").to_dicts()
            },
            home_regions=self._home_region_policy.home_regions_by_country(regions),
            region_locations=self._duration_policy.region_locations(regions),
        )

    def _process_order(
        self,
        order: dict[str, Any],
        batch: _ProductionCompletionBatch,
    ) -> None:
        eligible = self._eligible_order(order, batch)
        if eligible is None:
            return
        if not self._demilitarization_policy.can_add(
            batch.state,
            eligible.country_tag,
            eligible.quantity,
            unit_rows=batch.unit_rows,
        ):
            self._hold_order(order, batch)
            return

        home_region_id = batch.home_regions.get(
            str(eligible.country.get("id") or "")
        )
        if home_region_id is None:
            return
        self._create_deployment_group(order, eligible, home_region_id, batch)

    def _eligible_order(
        self,
        order: dict[str, Any],
        batch: _ProductionCompletionBatch,
    ) -> _EligibleProductionOrder | None:
        if not self._is_completion_candidate(order):
            return None
        eligible = self._resolve_order_context(order, batch)
        if eligible is None:
            return None
        if not self._design_belongs_to_country(eligible.design, eligible.country_tag):
            return None
        return eligible

    def _is_completion_candidate(self, order: dict[str, Any]) -> bool:
        return self._string_value(order.get("status")).lower() in {
            "completed",
            "held_by_demilitarization",
        }

    def _resolve_order_context(
        self,
        order: dict[str, Any],
        batch: _ProductionCompletionBatch,
    ) -> _EligibleProductionOrder | None:
        country_tag = self._string_value(order.get("country_id")).strip().upper()
        country = batch.countries_by_tag.get(country_tag)
        design = batch.designs_by_id.get(self._string_value(order.get("design_id")))
        quantity = max(0, self._integer_value(order.get("quantity")))
        if country is None or design is None or quantity <= 0:
            return None
        return _EligibleProductionOrder(country_tag, country, design, quantity)

    def _design_belongs_to_country(
        self,
        design: dict[str, Any],
        country_tag: str,
    ) -> bool:
        design_country = self._string_value(design.get("country_id")).strip().upper()
        return design_country == country_tag

    def _string_value(self, value: Any) -> str:
        return str(value or "")

    def _integer_value(self, value: Any) -> int:
        return int(value or 0)

    def _hold_order(
        self,
        order: dict[str, Any],
        batch: _ProductionCompletionBatch,
    ) -> None:
        order["status"] = "held_by_demilitarization"
        order["blocking_reason"] = (
            "Production is complete but delivery exceeds an active demilitarization limit."
        )
        batch.changed = True

    def _create_deployment_group(
        self,
        order: dict[str, Any],
        eligible: _EligibleProductionOrder,
        home_region_id: int,
        batch: _ProductionCompletionBatch,
    ) -> None:
        unit_type = self._unit_type(eligible.design)
        owner = str(eligible.country.get("id") or eligible.country_tag)
        origin_geo = batch.region_locations.get(
            home_region_id,
            GeoCoordinate(0.0, 0.0),
        )
        unit_id = self._unit_factory.next_id(
            batch.unit_rows,
            owner,
            unit_type,
        )
        unit = self._unit_factory.create_from_spec(
            UnitRecordSpec(
                unit_id=unit_id,
                owner=owner,
                unit_type=unit_type,
                strength=eligible.quantity,
                region_id=0,
                geo=GeoCoordinate(0.0, 0.0),
                current_minute=batch.state.time.total_minutes,
                design_id=str(order.get("design_id") or ""),
                training_level=str(order.get("requested_training_level") or "Recruit"),
            )
        )
        unit.update(
            source_region_id=home_region_id,
            source_latitude=origin_geo.latitude,
            source_longitude=origin_geo.longitude,
            production_order_id=str(order.get("id") or ""),
            original_cost=max(0.0, self._row_float(order, "unit_cost")) * eligible.quantity,
            unit_lifecycle="deployment_queued",
        )
        batch.unit_rows.append(unit)
        batch.deployment_rows.append(
            self._deployment_order_creator.create_order_record(
                DeploymentOrderSpec(
                    production_order_id=str(order.get("id") or ""),
                    unit_id=unit_id,
                    country_id=owner,
                    quantity=eligible.quantity,
                    source_region_id=home_region_id,
                    created_at_minute=int(batch.state.time.total_minutes),
                ),
                existing_deployments=batch.deployment_rows,
            )
        )
        eligible.country["military_count"] = (
            int(eligible.country.get("military_count") or 0) + eligible.quantity
        )
        order["status"] = "awaiting_deployment"
        order["blocking_reason"] = "Completed; waiting for deployment and route arrival."
        order["eta_days"] = 0
        batch.changed = True

    def _unit_type(self, design: dict[str, Any]) -> str:
        unit_type = (
            str(design.get("class_name") or DEFAULT_UNIT_TYPE)
            .strip()
            .lower()
            .replace(" ", "_")
        )
        return unit_type or DEFAULT_UNIT_TYPE

    def _row_float(
        self,
        row: dict[str, Any],
        key: str,
        fallback: Any = 0.0,
    ) -> float:
        value = row.get(key)
        if value is None:
            value = fallback
        try:
            return float(value if value is not None else 0.0)
        except (TypeError, ValueError):
            return 0.0
