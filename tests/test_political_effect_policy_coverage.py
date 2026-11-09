import polars as pl
import pytest

from modules.base.systems.politics.political_effect_policy import (
    aggregate_political_effects_by_type,
    bounded_ratio,
)


def _effect_row(country_id: str, value: str) -> dict[str, object]:
    return {
        "country_id": country_id,
        "domain": "tax",
        "effect": "rate",
        "value": value,
        "effective_at_minute": 0,
        "expires_at_minute": 0,
        "status": "active",
    }


def test_effect_aggregation_skips_invalid_values_nonfinite_values_and_empty_countries() -> None:
    effects = pl.DataFrame(
        [
            _effect_row("AAA", "not-a-number"),
            _effect_row("BBB", "inf"),
            _effect_row(" ", "0.4"),
            _effect_row("CCC", "0.2"),
        ]
    )

    result = aggregate_political_effects_by_type(
        effects,
        10,
        selectors={("tax", "rate")},
    )

    assert result == {("CCC", "tax", "rate"): 0.2}


def test_effect_aggregation_returns_empty_for_incomplete_schema() -> None:
    effects = pl.DataFrame({"country_id": ["AAA"], "value": [0.5]})

    assert aggregate_political_effects_by_type(
        effects,
        10,
        selectors={("tax", "rate")},
    ) == {}


def test_effect_aggregation_ignores_empty_inputs_and_inactive_rows() -> None:
    inactive_row = _effect_row("AAA", "0.5")
    inactive_row["status"] = "expired"

    assert aggregate_political_effects_by_type(
        None,
        10,
        selectors={("tax", "rate")},
    ) == {}
    assert aggregate_political_effects_by_type(
        pl.DataFrame([inactive_row]),
        10,
        selectors={("tax", "rate")},
    ) == {}


@pytest.mark.parametrize(
    ("value", "default"),
    [
        (None, 0.25),
        ("not-a-number", 0.4),
        (10**400, 0.6),
        (float("inf"), 0.75),
    ],
    ids=["none", "invalid-string", "overflow", "infinite"],
)
def test_bounded_ratio_uses_default_for_invalid_and_nonfinite_values(
    value: object,
    default: float,
) -> None:
    assert bounded_ratio(value, default) == default
