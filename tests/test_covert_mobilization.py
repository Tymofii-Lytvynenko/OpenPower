import pytest

from modules.base.systems.military.covert_mobilization import MobilizationFactors


def test_mobilization_scoring_preserves_probability_and_confidence_weights():
    factors = MobilizationFactors(
        skill_index=1, readiness=0.5, observer_telecom=0.4, target_telecom=0.6,
        signal_coverage=0.28, target_security=0.2, domestic_coverage=0.3,
    )
    assert factors.detection_probability() == pytest.approx(0.3736)
    assert factors.confidence() == pytest.approx(0.497)


def test_mobilization_scores_are_bounded_at_extremes():
    low = MobilizationFactors(0, 0.0, 0.0, 0.0, 0.0, 0.7, 1.0)
    high = MobilizationFactors(10, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0)
    assert low.detection_probability() == 0.02
    assert low.confidence() == pytest.approx(0.1)
    assert high.detection_probability() == 0.92
    assert high.confidence() == 0.95
