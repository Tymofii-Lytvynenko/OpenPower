from modules.base.systems.military.movement_duration import MovementDurationPolicy
from modules.base.systems.military.movement_order_policy import (
    MilitaryMovementOrderPolicy,
)
from src.shared.state import GameState


def test_movement_policy_handles_invalid_configuration_and_numeric_values() -> None:
    policy = MilitaryMovementOrderPolicy(MovementDurationPolicy())
    state = GameState(tables={})
    state.globals["military_domain_duration_multipliers"] = ["invalid"]

    assert policy.region_is_water({"terrain": "water"}) is True
    assert policy.bounded_multiplier(object(), default=1.5) == 1.5
    assert policy._domain_duration_multiplier(state, {"unit_type": "army"}) == 1.0
    assert policy._row_float({"coefficient": "bad"}, "coefficient") == 0.0
    assert policy._row_float_from_mapping(object(), default=2.25) == 2.25
