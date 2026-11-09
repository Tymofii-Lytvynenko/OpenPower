import polars as pl
import pytest

from modules.base.systems.economy import aligned_economy_fast_path as fast_path


def _frames(
    country_ids: tuple[str, ...] = ("AAA",),
    *,
    population_ids: tuple[str, ...] | None = None,
    optional_rates: bool = False,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    countries = [
        pl.Series("id", country_ids, dtype=pl.String),
        pl.Series("money_reserves", [100.0] * len(country_ids), dtype=pl.Float64),
    ]
    if optional_rates:
        countries.extend(
            (
                pl.Series("internal_tax_rate", [None] * len(country_ids), dtype=pl.Float64),
                pl.Series("industrial_growth_rate", [None] * len(country_ids), dtype=pl.Float64),
            )
        )
    country_frame = pl.DataFrame(countries)

    production_keys = [
        (country_id, resource_id)
        for country_id in country_ids
        for resource_id in fast_path._RESOURCE_ORDER
    ]
    production_frame = pl.DataFrame(
        {
            "country_id": pl.Series(
                [country_id for country_id, _ in production_keys], dtype=pl.String
            ),
            "game_resource_id": pl.Series(
                [resource_id for _, resource_id in production_keys], dtype=pl.String
            ),
            "domestic_production": pl.Series(
                [10.0] * len(production_keys), dtype=pl.Float64
            ),
        }
    )

    selected_population_ids = population_ids or country_ids
    population_frame = pl.DataFrame(
        {
            "country_id": pl.Series(selected_population_ids, dtype=pl.String),
            "population": pl.Series(
                [1000.0] * len(selected_population_ids), dtype=pl.Float64
            ),
        }
    )
    return country_frame, production_frame, population_frame


def _update(
    countries: pl.DataFrame,
    production: pl.DataFrame,
    population: pl.DataFrame,
    cache: fast_path.AlignedEconomyLayoutCache | None = None,
) -> fast_path.AlignedEconomyTables | None:
    return fast_path.update_aligned_economy_tables(
        countries,
        production,
        population,
        0.5,
        cache,
    )


def test_aligned_update_rejects_missing_schema_and_invalid_dtypes() -> None:
    countries, production, population = _frames()

    assert _update(
        pl.DataFrame({"id": ["AAA"]}), production, population
    ) is None
    assert _update(
        countries.with_columns(pl.Series("id", [1], dtype=pl.Int64)),
        production,
        population,
    ) is None
    assert _update(
        countries,
        production,
        population.with_columns(pl.col("population").cast(pl.String)),
    ) is None


def test_aligned_update_rejects_unsorted_keys_production_mismatch_and_duplicate_population() -> None:
    unsorted = _frames(("BBB", "AAA"))
    assert _update(*unsorted) is None

    countries, production, population = _frames()
    assert _update(countries, production.head(production.height - 1), population) is None

    duplicate_population = _frames(("AAA", "BBB"), population_ids=("AAA", "AAA", "BBB"))
    assert _update(*duplicate_population) is None


def test_aligned_update_rejects_metadata_that_does_not_match_canonical_resource_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    countries, production, population = _frames()
    monkeypatch.setattr(
        fast_path,
        "_RESOURCE_LEDGER_METADATA",
        fast_path._RESOURCE_LEDGER_METADATA.reverse(),
    )

    assert _update(countries, production, population) is None


@pytest.mark.parametrize("invalid_reserves", ["text", None])
def test_aligned_update_rejects_invalid_reserve_values(invalid_reserves: str | None) -> None:
    countries, production, population = _frames()
    if invalid_reserves is None:
        reserves = pl.Series("money_reserves", [None], dtype=pl.Float64)
    else:
        reserves = pl.Series("money_reserves", [invalid_reserves], dtype=pl.String)

    assert _update(countries.with_columns(reserves), production, population) is None


def test_aligned_update_fills_optional_numeric_defaults_and_reuses_layout_cache() -> None:
    countries, production, population = _frames()
    initial = _update(countries, production, population)

    assert initial is not None
    assert {"internal_tax_rate", "industrial_growth_rate", "economic_health"}.issubset(
        initial.countries.columns
    )

    updated_population = population.with_columns(
        pl.lit(2000.0).alias("population")
    )
    cached = _update(
        initial.countries,
        initial.production,
        updated_population,
        initial.layout_cache,
    )

    assert cached is not None
    assert cached.layout_cache is initial.layout_cache
    assert cached.countries["gdp_per_capita"][0] < initial.countries["gdp_per_capita"][0]


def test_aligned_update_fills_null_optional_rates_and_rejects_nonnumeric_production() -> None:
    countries, production, population = _frames(optional_rates=True)
    updated = _update(countries, production, population)

    assert updated is not None
    assert updated.countries["money_reserves"][0] == pytest.approx(
        100.0 + len(fast_path._RESOURCE_ORDER)
    )
    assert updated.production["domestic_production"][0] == pytest.approx(10.125)

    assert _update(
        countries,
        production.with_columns(
            pl.col("domestic_production").cast(pl.String)
        ),
        population,
    ) is None
