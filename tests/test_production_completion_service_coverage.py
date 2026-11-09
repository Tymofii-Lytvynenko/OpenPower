from __future__ import annotations

import polars as pl

from modules.base.systems.military.production_completion_service import (
    MilitaryProductionCompletionService,
)
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


class _UnitFactory:
    def next_id(self, unit_rows, country_tag, unit_type):
        return f"{country_tag}-{unit_type}-{len(unit_rows) + 1}"

    def create_from_spec(self, spec):
        return {
            "id": spec.unit_id,
            "owner": spec.owner,
            "strength": spec.strength,
        }


class _DemilitarizationPolicy:
    def __init__(self, allowed: bool):
        self.allowed = allowed

    def can_add(self, _state, _country_tag, _quantity, *, unit_rows):
        return self.allowed


class _DurationPolicy:
    def region_locations(self, _regions):
        return {1: GeoCoordinate(10.0, 20.0)}


class _DeploymentOrderCreator:
    def create_order_record(self, spec, existing_deployments):
        return {"id": f"deployment-{len(existing_deployments) + 1}", "unit_id": spec.unit_id}


class _HomeRegionPolicy:
    def __init__(self, home_regions):
        self.home_regions = home_regions

    def home_regions_by_country(self, _regions):
        return self.home_regions


def _service(*, allowed: bool = True, home_regions: dict[str, int] | None = None):
    return MilitaryProductionCompletionService(
        unit_factory=_UnitFactory(),
        demilitarization_policy=_DemilitarizationPolicy(allowed),
        duration_policy=_DurationPolicy(),
        deployment_order_creator=_DeploymentOrderCreator(),
        home_region_policy=_HomeRegionPolicy(
            {"USA": 1} if home_regions is None else home_regions
        ),
        ensure_country_columns=lambda frame: frame,
        units_from_rows=lambda rows: pl.DataFrame(rows),
    )


def _state(orders, designs=None):
    return GameState(
        tables={
            "countries": pl.DataFrame({"id": ["USA"], "military_count": [0]}),
            "regions": pl.DataFrame(
                {"id": [1], "owner": ["USA"], "latitude": [10.0], "longitude": [20.0]}
            ),
            "unit_designs": pl.DataFrame(
                designs
                or [{"id": "usa-design", "country_id": "USA", "class_name": "Infantry"}]
            ),
            "production_orders": pl.DataFrame(
                [
                    {
                        "id": order_id,
                        "country_id": country_id,
                        "design_id": design_id,
                        "quantity": quantity,
                        "status": status,
                        "requested_training_level": "Regular",
                        "unit_cost": unit_cost,
                        "blocking_reason": "",
                        "eta_days": 0,
                    }
                    for order_id, country_id, design_id, quantity, status, unit_cost in orders
                ]
            ),
        }
    )


def _order(
    order_id: str = "order-1",
    *,
    country_id: str = "USA",
    design_id: str = "usa-design",
    quantity: int = 2,
    status: str = "completed",
    unit_cost=None,
):
    return (order_id, country_id, design_id, quantity, status, unit_cost)


def test_completion_skips_missing_country_and_foreign_design_orders():
    state = _state(
        [
            _order("unknown-country", country_id="CAN"),
            _order("foreign-design", design_id="can-design"),
        ],
        designs=[
            {"id": "usa-design", "country_id": "USA", "class_name": "Infantry"},
            {"id": "can-design", "country_id": "CAN", "class_name": "Infantry"},
        ],
    )
    units = pl.DataFrame(schema={"id": pl.Utf8})

    result = _service().process_completed_orders(state, units)

    assert result is units
    assert state.get_table("production_orders")["status"].to_list() == [
        "completed",
        "completed",
    ]


def test_completion_holds_order_when_demilitarization_limit_blocks_delivery():
    state = _state([_order()])
    units = pl.DataFrame(schema={"id": pl.Utf8})

    _service(allowed=False).process_completed_orders(state, units)

    order = state.get_table("production_orders").row(0, named=True)
    assert order["status"] == "held_by_demilitarization"
    assert "active demilitarization limit" in order["blocking_reason"]


def test_completion_waits_when_country_has_no_home_region():
    state = _state([_order()])
    units = pl.DataFrame(schema={"id": pl.Utf8})

    result = _service(home_regions={}).process_completed_orders(state, units)

    assert result is units
    assert state.get_table("production_orders")["status"].to_list() == ["completed"]


def test_completion_defaults_missing_and_invalid_unit_costs_to_zero():
    state = _state(
        [
            _order("missing-cost", unit_cost=None),
            _order("invalid-cost", unit_cost="not-a-number"),
        ]
    )
    units = pl.DataFrame(schema={"id": pl.Utf8})

    result = _service().process_completed_orders(state, units)

    assert result.height == 2
    assert result["original_cost"].to_list() == [0.0, 0.0]
    assert state.get_table("production_orders")["status"].to_list() == [
        "awaiting_deployment",
        "awaiting_deployment",
    ]
