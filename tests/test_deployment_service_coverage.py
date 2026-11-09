from __future__ import annotations

from unittest.mock import Mock

import polars as pl
import pytest

from modules.base.systems.military import deployment_service as deployment_module
from modules.base.systems.military.deployment_service import MilitaryDeploymentService
from src.shared.actions import ActionDispatchUnitDeployment
from src.shared.state import GameState


def _service(*, authorized: bool = True) -> MilitaryDeploymentService:
    return MilitaryDeploymentService(
        unit_factory=Mock(),
        unit_order_workflow=Mock(),
        authorization_policy=lambda *_args: authorized,
        units_from_rows=pl.DataFrame,
    )


def _batch(service: MilitaryDeploymentService) -> deployment_module._DeploymentActionBatch:
    unit = {
        "id": "unit-1",
        "owner": "AAA",
        "strength": 1,
        "unit_lifecycle": "deployment_queued",
    }
    deployment = {"id": "deployment-1", "unit_id": "unit-1"}
    return deployment_module._DeploymentActionBatch(
        state=GameState(),
        current_minute=5,
        unit_rows=[unit],
        deployment_table=pl.DataFrame(
            schema={"id": pl.String, "unit_id": pl.String}
        ),
        deployments=[deployment],
        units_by_id={"unit-1": unit},
        deployments_by_unit={"unit-1": deployment},
        regions=pl.DataFrame({"id": [1]}),
    )


def _action(
    *,
    unit_id: str = "unit-1",
    destination_region_id: int = 1,
    quantity: int = 1,
) -> ActionDispatchUnitDeployment:
    return ActionDispatchUnitDeployment(
        player_id="player-1",
        unit_id=unit_id,
        destination_region_id=destination_region_id,
        quantity=quantity,
    )


def test_process_actions_returns_unchanged_units_when_batch_cannot_be_created() -> None:
    service = _service()
    state = GameState(current_actions=[_action()])
    units = pl.DataFrame({"id": ["unit-1"]})

    result, moves = service.process_actions(state, units)

    assert result is units
    assert moves == []


def test_process_action_records_missing_and_duplicate_unit_rejections() -> None:
    service = _service(authorized=False)
    batch = _batch(service)

    service._process_action(_action(unit_id="missing-unit"), batch)
    service._process_action(_action(), batch)
    service._process_action(_action(), batch)

    recorded = [call.args[1] for call in service._unit_order_workflow.record_feedback_entry.call_args_list]
    assert [entry.reason for entry in recorded] == [
        "No deployment-queued group matches this unit.",
        "The issuer does not control this deployment group.",
        "A unit group can receive only one deployment order per update.",
    ]


@pytest.mark.parametrize(
    ("authorized", "lifecycle", "destination", "quantity", "expected"),
    [
        (False, "deployment_queued", 1, 1, "The issuer does not control this deployment group."),
        (True, "available", 1, 1, "The unit is not waiting for deployment or route recovery."),
        (True, "deployment_queued", 0, 1, "The deployment destination is invalid."),
        (True, "deployment_queued", 1, 2, "The deployment quantity must be between one and the available group strength."),
    ],
)
def test_action_rejection_reason_reports_each_invalid_request(
    authorized: bool,
    lifecycle: str,
    destination: int,
    quantity: int,
    expected: str,
) -> None:
    service = _service(authorized=authorized)
    batch = _batch(service)
    batch.units_by_id["unit-1"]["unit_lifecycle"] = lifecycle

    reason = service._action_rejection_reason(
        _action(destination_region_id=destination, quantity=quantity),
        batch.units_by_id["unit-1"],
        "AAA",
        batch,
    )

    assert reason == expected


def test_destination_validation_rejects_missing_region_data() -> None:
    service = _service()

    assert service._destination_is_valid(None, 1) is False
    assert service._destination_is_valid(pl.DataFrame({"id": [1]}), 0) is False


def test_refresh_blocks_deployments_whose_unit_no_longer_exists() -> None:
    service = _service()
    deployment = {"unit_id": "missing-unit", "status": "dispatching"}

    service._refresh_deployment(deployment, {}, {})

    assert deployment == {
        "unit_id": "missing-unit",
        "status": "blocked",
        "blocking_reason": "The deployed group no longer exists.",
    }


@pytest.mark.parametrize(
    ("lifecycle", "route", "expected"),
    [
        ("deployment_blocked", {"rejection_reason": "No route."}, ("blocked", "No route.")),
        ("route_blocked", None, ("blocked", "The deployment route needs a new order.")),
        ("deployment_queued", None, ("queued", "Select a valid deployment region and dispatch this group.")),
        ("assembling", None, None),
    ],
)
def test_status_update_maps_lifecycle_to_deployment_status(
    lifecycle: str,
    route: dict[str, str] | None,
    expected: tuple[str, str] | None,
) -> None:
    assert _service()._status_update(lifecycle, route) == expected
