import pytest

from src.engine.clock import FixedStepClock


@pytest.mark.parametrize(
    "configuration,message",
    [
        ({"step_seconds": 0.0}, "Fixed step duration must be positive"),
        ({"max_catch_up_steps": 0}, "max_catch_up_steps must be at least one"),
    ],
)
def test_fixed_step_clock_rejects_invalid_limits(configuration, message):
    with pytest.raises(ValueError, match=message):
        FixedStepClock(**configuration)
