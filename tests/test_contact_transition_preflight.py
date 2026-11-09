import polars as pl
import pytest

from modules.base.systems.military.contact_transition_preflight import (
    MilitaryContactTransitionPreflight,
)
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionAttackUnit
from src.shared.state import GameState


class _ReadinessTransitions:
    def __init__(self) -> None:
        self.cancellations: list[tuple[str, str]] = []

    def cancel_transition_for_unit(
        self,
        _state: GameState,
        unit_id: str,
        reason: str,
    ) -> None:
        self.cancellations.append((unit_id, reason))


class _UnitOrderWorkflow:
    def __init__(self, transitioning: bool = False) -> None:
        self.transitioning = transitioning

    def unit_is_transitioning(self, _state: GameState, _unit_id: str) -> bool:
        return self.transitioning


class _UnitMovement:
    def __init__(self) -> None:
        self.contact: tuple[dict, float] | None = None
        self.calls: list[tuple[GeoCoordinate, GeoCoordinate, int]] = []

    def first_hostile_contact(
        self,
        _moving_unit: dict,
        _unit_rows: list[dict],
        start: GeoCoordinate,
        end: GeoCoordinate,
        current_minute: int,
    ) -> tuple[dict, float] | None:
        self.calls.append((start, end, current_minute))
        return self.contact


def _unit(unit_id: str, owner: str) -> dict:
    return {
        "id": unit_id,
        "owner": owner,
        "strength": 100,
        "readiness_status": "ready",
        "engagement_mode": "",
        "is_moving": False,
    }


def _setup(*, transitioning: bool = False):
    readiness = _ReadinessTransitions()
    movement = _UnitMovement()
    service = MilitaryContactTransitionPreflight(
        readiness_transitions=readiness,
        unit_order_workflow=_UnitOrderWorkflow(transitioning),
        unit_movement=movement,
        hostility_policy=lambda _rows: {frozenset(("USA", "CAN"))},
    )
    state = GameState(tables={"countries_wars": pl.DataFrame(schema={"id": pl.Int32})})
    return service, state, readiness, movement


def test_valid_hostile_attack_cancels_both_contacting_units():
    service, state, readiness, _movement = _setup()
    units = pl.DataFrame([_unit("USA-1", "USA"), _unit("CAN-1", "CAN")])
    state.current_actions = [ActionAttackUnit("USA", "USA-1", "CAN-1")]

    service.process(state, units)

    assert readiness.cancellations == [
        ("CAN-1", "combat_contact"),
        ("USA-1", "combat_contact"),
    ]


def test_invalid_attack_does_not_cancel_readiness_transitions():
    service, state, readiness, _movement = _setup()
    units = pl.DataFrame([_unit("USA-1", "USA"), _unit("CAN-1", "CAN")])
    state.current_actions = [ActionAttackUnit("USA", "USA-1", "missing")]

    service.process(state, units)

    assert readiness.cancellations == []


def test_predicted_movement_contact_uses_current_and_next_segment_positions():
    service, state, readiness, movement = _setup()
    moving_unit = _unit("USA-1", "USA")
    moving_unit.update(
        is_moving=True,
        latitude=0.0,
        longitude=0.0,
        source_latitude=0.0,
        source_longitude=0.0,
        target_latitude=0.0,
        target_longitude=10.0,
        departed_at_minute=0,
        arrival_at_minute=100,
        movement_progress=0.0,
    )
    enemy = _unit("CAN-1", "CAN")
    movement.contact = (enemy, 0.5)
    state.time.total_minutes = 50

    service.process(state, pl.DataFrame([moving_unit, enemy]))

    assert movement.calls == [
        (GeoCoordinate(0.0, 0.0), GeoCoordinate(0.0, 5.0), 50),
    ]
    assert readiness.cancellations == [
        ("CAN-1", "combat_contact"),
        ("USA-1", "combat_contact"),
    ]


def test_non_hostile_units_are_skipped_before_contact_processing():
    service, state, readiness, _movement = _setup()

    service.process(state, pl.DataFrame([_unit("MEX-1", "MEX")]))

    assert readiness.cancellations == []


def test_attacking_unit_in_transition_cannot_start_contact():
    service, state, readiness, _movement = _setup(transitioning=True)
    units = pl.DataFrame([_unit("USA-1", "USA"), _unit("CAN-1", "CAN")])
    state.current_actions = [ActionAttackUnit("USA", "USA-1", "CAN-1")]

    service.process(state, units)

    assert readiness.cancellations == []


def test_moving_unit_without_hostile_candidates_does_not_query_movement():
    service, state, readiness, movement = _setup()
    moving_unit = _unit("USA-1", "USA")
    moving_unit["is_moving"] = True

    service.process(state, pl.DataFrame([moving_unit]))

    assert movement.calls == []
    assert readiness.cancellations == []


def test_hostile_attack_rejects_same_unit_and_inactive_strength():
    service, _state, _readiness, _movement = _setup()
    attacker = _unit("USA-1", "USA")
    defender = _unit("CAN-1", "CAN")
    hostile_pairs = {frozenset(("USA", "CAN"))}

    assert not service.valid_hostile_attack(attacker, attacker, hostile_pairs)

    attacker["strength"] = 0
    assert not service.valid_hostile_attack(attacker, defender, hostile_pairs)

    attacker["strength"] = 100
    defender["strength"] = 0
    assert not service.valid_hostile_attack(attacker, defender, hostile_pairs)


def test_movement_coordinates_fall_back_and_invalid_numbers_become_zero():
    service, _state, _readiness, _movement = _setup()
    row = {"latitude": 12.5, "longitude": -35.0}

    assert service._movement_segment(row, 60) == (
        GeoCoordinate(12.5, -35.0),
        GeoCoordinate(12.5, -35.0),
    )
    assert service._row_float({"latitude": "invalid"}, "latitude") == 0.0
