import math

import pytest

from src.client.ui.panels.service.news_panel import NewsPanel


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 1.0),
        ("invalid", 1.0),
        (math.nan, 1.0),
        (math.inf, 1.0),
        (-2.0, 0.0),
        (8.0, 4.0),
        ("2.25", 2.25),
    ],
)
def test_frequency_setting_is_safe_and_bounded(value, expected):
    assert NewsPanel._read_frequency_multiplier(value) == expected


@pytest.mark.parametrize(
    ("value", "fallback", "expected"),
    [
        (None, 17, 17),
        ("invalid", 17, 17),
        (math.nan, 17, 17),
        (-4, 17, 0),
        ((1 << 70), 17, (1 << 63) - 1),
        (42, 17, 42),
    ],
)
def test_seed_setting_uses_safe_fallback_and_supported_range(value, fallback, expected):
    assert NewsPanel._read_seed(value, fallback) == expected


def test_boolean_setting_does_not_treat_corrupt_strings_as_enabled_or_disabled():
    assert NewsPanel._read_bool(False, True) is False
    assert NewsPanel._read_bool("false", True) is True
    assert NewsPanel._read_bool(None, False) is False
