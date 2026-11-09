import polars as pl
import pytest

from src.client.visualization.map_modes.gradient_mode import GradientMapMode
from src.shared.state import GameState


def make_state(**tables: pl.DataFrame) -> GameState:
    state = GameState()
    for name, frame in tables.items():
        state.update_table(name, frame)
    return state


def test_map_mode_exposes_configuration_and_returns_empty_without_regions() -> None:
    mode = GradientMapMode("GDP per capita", "gdp")

    assert mode.name == "GDP per capita"
    assert mode.merge_borders is True
    assert mode.calculate_colors(make_state()) == {}


def test_calculate_colors_uses_region_values_and_marks_null_values_gray() -> None:
    state = make_state(
        regions=pl.DataFrame(
            {"id": [1, 2, 3], "gdp": [0.0, 10.0, None]}
        )
    )

    assert GradientMapMode("GDP", "gdp").calculate_colors(state) == {
        1: (0, 0, 255),
        2: (255, 0, 0),
        3: (40, 40, 40),
    }


def test_calculate_colors_falls_back_to_country_values_when_enabled() -> None:
    state = make_state(
        regions=pl.DataFrame({"id": [1, 2], "owner": ["USA", "CAN"]}),
        countries=pl.DataFrame({"id": ["USA", "CAN"], "gdp": [0.0, 10.0]}),
    )

    mode = GradientMapMode("GDP", "gdp", fallback_to_country=True)

    assert mode.calculate_colors(state) == {1: (0, 0, 255), 2: (255, 0, 0)}


@pytest.mark.parametrize(
    ("mode", "state"),
    [
        (
            GradientMapMode("GDP", "gdp", fallback_to_country=False),
            make_state(regions=pl.DataFrame({"id": [1], "owner": ["USA"]})),
        ),
        (
            GradientMapMode("GDP", "gdp"),
            make_state(
                regions=pl.DataFrame({"id": [1], "owner": ["USA"]}),
                countries=pl.DataFrame({"id": ["USA"], "population": [10]}),
            ),
        ),
    ],
    ids=["fallback-disabled", "country-column-missing"],
)
def test_calculate_colors_returns_empty_when_target_column_cannot_be_resolved(
    mode: GradientMapMode,
    state: GameState,
) -> None:
    assert mode.calculate_colors(state) == {}


def test_calculate_colors_returns_empty_when_all_target_values_are_null() -> None:
    state = make_state(regions=pl.DataFrame({"id": [1, 2], "gdp": [None, None]}))

    assert GradientMapMode("GDP", "gdp").calculate_colors(state) == {}


def test_percentile_mode_assigns_equal_dense_ranks_and_keeps_nulls_gray() -> None:
    state = make_state(
        regions=pl.DataFrame({"id": [1, 2, 3, 4], "gdp": [10.0, 10.0, 30.0, None]})
    )

    mode = GradientMapMode("GDP", "gdp", use_percentile=True)

    assert mode.calculate_colors(state) == {
        1: (0, 0, 255),
        2: (0, 0, 255),
        3: (255, 0, 0),
        4: (40, 40, 40),
    }


def test_percentile_mode_centers_a_single_dense_rank() -> None:
    state = make_state(regions=pl.DataFrame({"id": [1, 2], "gdp": [10.0, 10.0]}))

    mode = GradientMapMode("GDP", "gdp", use_percentile=True)

    assert mode.calculate_colors(state) == {1: (0, 255, 0), 2: (0, 255, 0)}


def test_linear_mode_handles_equal_values_without_dividing_by_zero() -> None:
    state = make_state(regions=pl.DataFrame({"id": [1, 2], "gdp": [10.0, 10.0]}))

    assert GradientMapMode("GDP", "gdp").calculate_colors(state) == {
        1: (0, 0, 255),
        2: (0, 0, 255),
    }


def test_steps_quantize_linear_colors_into_even_bands() -> None:
    state = make_state(
        regions=pl.DataFrame({"id": [1, 2, 3, 4], "gdp": [0.0, 1.0, 3.0, 4.0]})
    )

    mode = GradientMapMode("GDP", "gdp", steps=2)

    assert mode.calculate_colors(state) == {
        1: (0, 0, 255),
        2: (0, 0, 255),
        3: (0, 255, 0),
        4: (255, 0, 0),
    }
