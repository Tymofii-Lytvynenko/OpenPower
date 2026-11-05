from types import SimpleNamespace

import pytest

from modules.base.systems.military.covert_mission_start import plan_mission_start
from src.shared.actions import ActionStartCovertMission


def _action(**overrides):
    values = {
        "player_id": "player-1",
        "cell_id": "cell-1",
        "mission_type": "civilian_espionage",
        "target_country_tag": "CAN",
    }
    values.update(overrides)
    return ActionStartCovertMission(**values)


def _cell(**overrides):
    cell = {
        "id": "cell-1",
        "country_id": "USA",
        "target_country_id": "CAN",
        "location_country_id": "CAN",
        "communications_ready": True,
        "status": "active",
        "assignment": "unassigned",
        "skill_level": "Elite",
    }
    cell.update(overrides)
    return cell


def _plan(
    action=None,
    *,
    cells=None,
    countries=None,
    missions=(),
    authorized=True,
):
    state = SimpleNamespace(globals={}, tables={})
    countries = countries or [
        {"id": "USA", "money_reserves": 100.0},
        {"id": "CAN", "money_reserves": 100.0},
    ]
    result = plan_mission_start(
        state,
        [_cell()] if cells is None else cells,
        countries,
        list(missions),
        action or _action(),
        normalize_tag=lambda value: str(value or "").strip().upper(),
        finite_number=lambda value: _finite(value),
        is_authorized=lambda _state, player, country: (
            authorized and player == "player-1" and country == "USA"
        ),
    )
    return result, countries


def _finite(value):
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def test_mission_start_plan_is_validated_without_mutating_simulation_rows():
    result, countries = _plan(
        _action(requires_execution_confirmation=True, complexity="high")
    )

    assert result.rejection_reason == ""
    assert result.plan is not None
    assert result.plan.mission_type == "civilian_espionage"
    assert result.plan.target_sector == "civilian"
    assert result.plan.assignment == "espionage"
    assert result.plan.execution_cost == 2.0
    assert result.plan.requires_execution_confirmation is True
    assert result.plan.preparation_minutes > 0
    assert countries[0]["money_reserves"] == 100.0


@pytest.mark.parametrize(
    ("action", "expected_reason"),
    [
        (
            _action(target_sector="military"),
            "The target sector does not match the selected mission profile.",
        ),
        (
            _action(target_resource_id="unknown-resource"),
            "Choose a resource available to the target country.",
        ),
        (
            _action(mission_type="military_sabotage", target_unit_category="unknown"),
            "Choose a unit category available for a military mission.",
        ),
        (
            _action(cover_country_tag="ZZZ"),
            "Choose an existing country other than the mission target to frame.",
        ),
        (
            _action(requires_execution_confirmation=1),
            "Choose a boolean mission execution mode.",
        ),
    ],
)
def test_mission_start_plan_returns_validation_reason(action, expected_reason):
    result, _ = _plan(action)

    assert result.plan is None
    assert result.rejection_reason == expected_reason


def test_mission_start_plan_rejects_unavailable_cell_authority_duplicate_and_funding():
    unauthorized, _ = _plan(authorized=False)
    occupied, _ = _plan(missions=[{"cell_id": "cell-1", "status": "cleanup"}])
    unfunded, _ = _plan(
        countries=[
            {"id": "USA", "money_reserves": 1.0},
            {"id": "CAN", "money_reserves": 100.0},
        ]
    )

    assert unauthorized.rejection_reason == (
        "The issuer cannot command this cell or the cell is unavailable."
    )
    assert occupied.rejection_reason == (
        "The target does not match the assignment or this cell already has an active mission."
    )
    assert unfunded.rejection_reason == "The owner cannot fund mission preparation."
