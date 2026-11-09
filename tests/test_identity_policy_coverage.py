import pytest

from modules.base.systems.politics.identity_policy import (
    _share,
    apply_identity_assimilation,
)


def test_assimilation_skips_suppressed_groups_without_a_legal_destination():
    groups = [
        {
            "country_id": "AAA",
            "identity_type": "language",
            "identity_id": "minority",
            "legal_status": "restricted",
            "population_share": 40.0,
        }
    ]

    assert apply_identity_assimilation(groups, 525_600) == []
    assert groups[0]["population_share"] == 40.0


def test_assimilation_treats_invalid_update_minute_as_epoch_zero():
    groups = [
        {
            "country_id": "AAA",
            "identity_type": "language",
            "identity_id": "suppressed",
            "legal_status": "illegal",
            "population_share": 40.0,
            "last_updated_minute": "invalid",
        },
        {
            "country_id": "AAA",
            "identity_type": "language",
            "identity_id": "recognized",
            "legal_status": "legal",
            "population_share": 60.0,
        },
    ]

    changes = apply_identity_assimilation(groups, 525_600)

    assert len(changes) == 1
    assert changes[0]["share_points"] == pytest.approx(0.8, rel=0.002)
    assert groups[0]["last_updated_minute"] == 525_600


def test_invalid_identity_share_defaults_to_zero():
    assert _share("not-a-percentage") == 0.0
