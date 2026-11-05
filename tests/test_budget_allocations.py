import math

import pytest

from src.client.ui.panels.budget_allocations import (
    country_budget_allocations,
    default_budget_allocations,
    normalize_budget_ratio,
)


def test_default_budget_allocations_initialize_sectors_and_tax_rate():
    allocations = default_budget_allocations(
        ["budget_health_ratio", "budget_edu_ratio"], "personal_income_tax_rate"
    )

    assert allocations == {
        "budget_health_ratio": 0.5,
        "budget_edu_ratio": 0.5,
        "personal_income_tax_rate": 0.2,
    }


def test_country_budget_allocations_default_missing_and_invalid_fields():
    allocations = country_budget_allocations(
        {
            "budget_health_ratio": 1.4,
            "budget_edu_ratio": math.nan,
            "personal_income_tax_rate": "invalid",
        },
        ["budget_health_ratio", "budget_edu_ratio"],
        "personal_income_tax_rate",
    )

    assert allocations == {
        "budget_health_ratio": 1.0,
        "budget_edu_ratio": 0.5,
        "personal_income_tax_rate": 0.2,
    }


def test_country_budget_allocations_returns_none_for_unavailable_country():
    assert country_budget_allocations(
        None, ["budget_health_ratio"], "personal_income_tax_rate"
    ) is None


@pytest.mark.parametrize(
    ("value", "fallback", "expected"),
    [
        (-0.3, 0.4, 0.0),
        (2.5, 0.4, 1.0),
        (math.inf, 0.4, 0.4),
        (None, 0.4, 0.4),
    ],
)
def test_normalize_budget_ratio_bounds_values_and_uses_fallback(value, fallback, expected):
    assert normalize_budget_ratio(value, fallback) == expected
