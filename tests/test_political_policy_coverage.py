import polars as pl
import pytest

from modules.base.systems.politics.political_policy import (
    _append_rows,
    _finite,
    _frame_like,
    _non_negative_int,
    clamp_percent,
    initialize_country_politics,
)


def test_political_initialization_handles_missing_frames_and_blank_country_ids() -> None:
    empty = initialize_country_politics(None, None, None, None, 0)
    blank_id = initialize_country_politics(
        pl.DataFrame({"id": [""]}),
        None,
        None,
        None,
        0,
    )

    assert all(frame.is_empty() for frame in empty)
    assert all(frame.is_empty() for frame in blank_id)


def test_percentage_and_numeric_helpers_normalize_invalid_values() -> None:
    assert clamp_percent(0.25) == 25.0
    assert clamp_percent(75.0) == 75.0
    assert clamp_percent(-5.0) == 0.0
    assert clamp_percent(150.0) == 100.0
    assert _non_negative_int("invalid") == 0
    assert _finite(float("nan"), 0.75) == 0.75


def test_frame_helpers_build_frames_when_no_template_exists() -> None:
    appended = _append_rows(None, [{"country_id": "AAA"}])
    shaped = _frame_like(None, [{"country_id": "BBB"}])

    assert appended.to_dicts() == [{"country_id": "AAA"}]
    assert shaped.to_dicts() == [{"country_id": "BBB"}]


@pytest.mark.parametrize("value", [None, pl.DataFrame(), pl.DataFrame({"tag": ["AAA"]})])
def test_political_initialization_returns_empty_frames_for_missing_country_schema(
    value: pl.DataFrame | None,
) -> None:
    initialized = initialize_country_politics(
        value,
        None,
        None,
        None,
        0,
    )

    assert all(frame.is_empty() for frame in initialized)
