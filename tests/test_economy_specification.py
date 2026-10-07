from __future__ import annotations

import math

import numpy as np
import polars as pl
import pytest

from modules.base.systems.economy.budget_system import BudgetSystem
from modules.base.systems.economy.consumption_fast_path import (
    ConsumptionLayoutCache,
    calculate_formulaic_consumption,
)
from modules.base.systems.economy.internal_economy_system import InternalEconomySystem
from modules.base.systems.economy.trade_system import TradeSystem
from src.shared.economy_meta import RESOURCE_MAPPING
from src.shared.numeric import (
    stable_group_sum,
    stable_group_sums,
    stable_nonnegative_row_totals,
)
from src.shared.frames import ensure_sorted
from src.shared.events import EventRealSecond
from src.shared.state import GameState


def test_consumption_pool_matches_global_wealth_anchor_and_protects_basic_food_demand():
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["POOR", "RICH"],
                    "gdp_per_capita": [100.0, 10_000.0],
                    "poverty_rate": [0.3, 0.05],
                    "human_dev": [0.5, 0.9],
                    "real_income_index": [1.0, 1.0],
                    "economic_trade_modifier": [1.0, 1.0],
                }
            ),
            "regions": pl.DataFrame(
                {
                    "owner": ["POOR", "RICH"],
                    "pop_14": [200, 200],
                    "pop_15_64": [700, 700],
                    "pop_65": [100, 100],
                }
            ),
        }
    )
    demand = InternalEconomySystem()._calculate_formulaic_consumption(state)
    totals = demand.group_by("country_id").agg(
        pl.col("consumption_usd").sum().alias("total")
    )
    by_country_resource = {
        (row["country_id"], row["game_resource_id"]): row["consumption_usd"]
        for row in demand.iter_rows(named=True)
    }

    global_average = (100.0 * 1_000 + 10_000.0 * 1_000) / 2_000
    expected = {}
    for country, gdppc in (("POOR", 100.0), ("RICH", 10_000.0)):
        wealth_index = min(10.0, max(0.05, gdppc / global_average))
        expected[country] = 1_000 * gdppc * (
            0.50 + 0.40 / (1.0 + wealth_index)
        )

    actual_totals = {row["country_id"]: row["total"] for row in totals.iter_rows(named=True)}
    assert math.isclose(actual_totals["POOR"], expected["POOR"], rel_tol=1e-12)
    assert math.isclose(actual_totals["RICH"], expected["RICH"], rel_tol=1e-12)
    assert by_country_resource[("POOR", "cereals")] > 0.0
    assert by_country_resource[("RICH", "cereals")] > 0.0
    assert (
        by_country_resource[("POOR", "luxury_commodities")] / actual_totals["POOR"]
        < by_country_resource[("RICH", "luxury_commodities")] / actual_totals["RICH"]
    )


def test_consumption_pool_uses_authoritative_total_gdp_when_available():
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["POOR", "RICH", "MISSING_GDP"],
                    "gdp": [100_000.0, 5_000_000.0, None],
                    "gdp_per_capita": [100.0, 10_000.0, 500.0],
                    "poverty_rate": [0.3, 0.05, 0.2],
                    "human_dev": [0.5, 0.9, 0.6],
                    "real_income_index": [1.0, 1.0, 1.0],
                    "economic_trade_modifier": [1.0, 1.0, 1.0],
                }
            ),
            "regions": pl.DataFrame(
                {
                    "owner": ["POOR", "RICH", "MISSING_GDP"],
                    "pop_14": [200, 200, 200],
                    "pop_15_64": [700, 700, 700],
                    "pop_65": [100, 100, 100],
                }
            ),
        }
    )

    demand = InternalEconomySystem()._calculate_formulaic_consumption(state)
    totals = {
        row["country_id"]: row["consumption_usd"]
        for row in demand.group_by("country_id").agg(pl.col("consumption_usd").sum()).iter_rows(named=True)
    }
    global_average = (100_000.0 + 5_000_000.0 + 500_000.0) / 3_000.0
    expected = {}
    for country, gdp, gdp_per_capita in (
        ("POOR", 100_000.0, 100.0),
        ("RICH", 5_000_000.0, 10_000.0),
        ("MISSING_GDP", 500_000.0, 500.0),
    ):
        wealth_index = min(10.0, max(0.05, gdp_per_capita / global_average))
        expected[country] = gdp * (0.50 + 0.40 / (1.0 + wealth_index))

    for country, expected_total in expected.items():
        assert math.isclose(totals[country], expected_total, rel_tol=1e-12)


def test_vectorized_consumption_matches_the_polars_compatibility_path(monkeypatch):
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["POOR", "RICH", "MISSING_GDP"],
                    "gdp": [100_000.0, 5_000_000.0, None],
                    "gdp_per_capita": [100.0, 10_000.0, 500.0],
                    "poverty_rate": [0.3, 0.05, 0.2],
                    "human_dev": [0.5, 0.9, 0.6],
                    "real_income_index": [1.0, 1.0, 1.0],
                    "economic_trade_modifier": [1.0, 1.0, 1.0],
                }
            ),
            "regions": pl.DataFrame(
                {
                    "owner": ["POOR", "RICH", "MISSING_GDP"],
                    "pop_14": [200, 200, 200],
                    "pop_15_64": [700, 700, 700],
                    "pop_65": [100, 100, 100],
                }
            ),
        }
    )
    optimized = InternalEconomySystem()._calculate_formulaic_consumption(state)
    monkeypatch.setattr(
        "modules.base.systems.economy.internal_economy_system.calculate_formulaic_consumption_fast",
        lambda *args: None,
    )
    compatible = InternalEconomySystem()._calculate_formulaic_consumption(state)

    optimized = optimized.sort("country_id", "game_resource_id")
    compatible = compatible.sort("country_id", "game_resource_id")
    assert optimized.select("country_id", "game_resource_id").equals(
        compatible.select("country_id", "game_resource_id")
    )
    assert all(
        math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9)
        for actual, expected in zip(
            optimized.get_column("consumption_usd").to_list(),
            compatible.get_column("consumption_usd").to_list(),
            strict=True,
        )
    )


def test_formulaic_consumption_is_invariant_to_country_and_region_input_order():
    countries = pl.DataFrame(
        {
            "id": ["AAA", "BBB", "CCC"],
            "gdp": [1_000_000.0, 7_000_000.0, 250_000.0],
            "gdp_per_capita": [1_000.0, 7_000.0, 250.0],
            "poverty_rate": [0.1, 0.05, 0.4],
            "human_dev": [0.7, 0.95, 0.3],
            "real_income_index": [1.0, 1.2, 0.8],
            "economic_trade_modifier": [1.0, 0.9, 0.75],
        }
    )
    regions = pl.DataFrame(
        {
            "owner": ["AAA", "BBB", "CCC", "AAA", "CCC"],
            "pop_14": [10, 20, 5, 4, 8],
            "pop_15_64": [50, 100, 25, 20, 40],
            "pop_65": [5, 10, 2, 2, 4],
        }
    )

    ordered = GameState(tables={"countries": countries, "regions": regions})
    permuted = GameState(
        tables={
            "countries": countries.reverse(),
            "regions": regions.reverse(),
        }
    )

    ordered_output = InternalEconomySystem()._calculate_formulaic_consumption(ordered)
    permuted_output = InternalEconomySystem()._calculate_formulaic_consumption(permuted)
    ordered_output = ordered_output.sort("country_id", "game_resource_id")
    permuted_output = permuted_output.sort("country_id", "game_resource_id")

    assert ordered_output.select("country_id", "game_resource_id").equals(
        permuted_output.select("country_id", "game_resource_id")
    )
    assert ordered_output.get_column("consumption_usd").to_list() == pytest.approx(
        permuted_output.get_column("consumption_usd").to_list(), rel=1e-12, abs=1e-9
    )


def test_formulaic_consumption_reuses_only_identifier_layout_and_refreshes_values():
    countries = pl.DataFrame(
        {
            "id": ["BBB", "AAA"],
            "gdp": [700_000.0, 300_000.0],
            "gdp_per_capita": [700.0, 300.0],
            "poverty_rate": [0.1, 0.2],
            "human_dev": [0.8, 0.6],
        }
    )
    population = pl.DataFrame(
        {"country_id": ["AAA", "BBB"], "population": [1_000, 1_000]}
    )
    cache = ConsumptionLayoutCache()

    first = calculate_formulaic_consumption(
        countries,
        population,
        InternalEconomySystem.CONSUMPTION_FORMULAS,
        tuple(RESOURCE_MAPPING),
        cache,
    )
    original_layout = cache.layout
    assert first is not None
    assert original_layout is not None

    updated_population = population.with_columns(
        pl.Series("population", [2_000, 1_000])
    )
    second = calculate_formulaic_consumption(
        countries,
        updated_population,
        InternalEconomySystem.CONSUMPTION_FORMULAS,
        tuple(RESOURCE_MAPPING),
        cache,
    )
    assert second is not None
    assert cache.layout is original_layout
    assert second.get_column("consumption_usd").to_list() != first.get_column(
        "consumption_usd"
    ).to_list()

    permuted_countries = countries.reverse()
    third = calculate_formulaic_consumption(
        permuted_countries,
        updated_population,
        InternalEconomySystem.CONSUMPTION_FORMULAS,
        tuple(RESOURCE_MAPPING),
        cache,
    )
    assert third is not None
    assert cache.layout is not original_layout
    assert third.select("country_id", "game_resource_id").equals(
        second.select("country_id", "game_resource_id")
    )


@pytest.mark.parametrize(
    ("column", "value"),
    [("gdp", float("inf")), ("gdp_per_capita", float("nan"))],
)
def test_formulaic_consumption_rejects_non_finite_required_metrics(column, value):
    countries = pl.DataFrame(
        {
            "id": ["AAA"],
            "gdp": [100_000.0],
            "gdp_per_capita": [1_000.0],
            "poverty_rate": [0.1],
            "human_dev": [0.8],
            "real_income_index": [1.0],
            "economic_trade_modifier": [1.0],
        }
    ).with_columns(pl.lit(value).alias(column))
    state = GameState(
        tables={
            "countries": countries,
            "regions": pl.DataFrame(
                {"owner": ["AAA"], "pop_14": [0], "pop_15_64": [100], "pop_65": [0]}
            ),
        }
    )

    with pytest.raises(ValueError, match="finite"):
        InternalEconomySystem()._calculate_formulaic_consumption(state)


def test_formulaic_consumption_validates_countries_without_population_rows():
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA", "UNMATCHED"],
                    "gdp": [100_000.0, float("inf")],
                    "gdp_per_capita": [1_000.0, 1_000.0],
                    "poverty_rate": [0.1, 0.1],
                    "human_dev": [0.8, 0.8],
                    "real_income_index": [1.0, 1.0],
                    "economic_trade_modifier": [1.0, 1.0],
                }
            ),
            "regions": pl.DataFrame(
                {"owner": ["AAA"], "pop_14": [0], "pop_15_64": [100], "pop_65": [0]}
            ),
        }
    )

    with pytest.raises(ValueError, match="countries columns must contain finite"):
        InternalEconomySystem()._calculate_formulaic_consumption(state)


def test_formulaic_consumption_returns_zero_demand_for_empty_and_zero_population():
    countries = pl.DataFrame(
        {
            "id": ["EMPTY", "ZERO"],
            "gdp": [0.0, 0.0],
            "gdp_per_capita": [0.0, 1_000.0],
            "poverty_rate": [0.0, 0.0],
            "human_dev": [0.5, 0.5],
        }
    )
    empty_state = GameState(
        tables={
            "countries": countries,
            "regions": pl.DataFrame(
                schema={
                    "owner": pl.Utf8,
                    "pop_14": pl.Int64,
                    "pop_15_64": pl.Int64,
                    "pop_65": pl.Int64,
                }
            ),
        }
    )
    zero_population_state = GameState(
        tables={
            "countries": countries,
            "regions": pl.DataFrame(
                {"owner": ["ZERO"], "pop_14": [0], "pop_15_64": [0], "pop_65": [0]}
            ),
        }
    )

    assert InternalEconomySystem()._calculate_formulaic_consumption(empty_state).is_empty()
    zero_demand = InternalEconomySystem()._calculate_formulaic_consumption(zero_population_state)
    assert zero_demand.get_column("consumption_usd").to_list() == [0.0] * len(RESOURCE_MAPPING)


def test_formulaic_consumption_clips_wealth_index_at_both_extremes():
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["VERY_POOR", "VERY_RICH"],
                    "gdp": [1_000.0, 1_000_000_000.0],
                    "gdp_per_capita": [1.0, 1_000_000_000.0],
                    "poverty_rate": [0.0, 0.0],
                    "human_dev": [1.0, 1.0],
                }
            ),
            "regions": pl.DataFrame(
                {
                    "owner": ["VERY_POOR", "VERY_RICH"],
                    "pop_14": [0, 0],
                    "pop_15_64": [1_000, 1],
                    "pop_65": [0, 0],
                }
            ),
        }
    )

    demand = InternalEconomySystem()._calculate_formulaic_consumption(state)
    totals = {
        row["country_id"]: row["total"]
        for row in demand.group_by("country_id").agg(
            pl.col("consumption_usd").sum().alias("total")
        ).iter_rows(named=True)
    }
    global_average = (1_000.0 + 1_000_000_000.0) / 1_001.0
    assert totals["VERY_POOR"] == pytest.approx(
        1_000.0 * (0.50 + 0.40 / (1.0 + 0.05)), rel=1e-12
    )
    assert totals["VERY_RICH"] == pytest.approx(
        1_000_000_000.0 * (0.50 + 0.40 / (1.0 + 10.0)), rel=1e-12
    )
    assert global_average > 100.0


def test_formulaic_consumption_rejects_cyclic_dependencies_and_ignores_missing_catalog_entries():
    countries = pl.DataFrame(
        {"id": ["AAA"], "gdp": [100.0], "gdp_per_capita": [100.0]}
    )
    population = pl.DataFrame({"country_id": ["AAA"], "population": [1.0]})
    formulas = {
        "resource_a": {
            "solvent_base_consumption": 1.0,
            "general_base_consumption": 1.0,
            "output_multiplier": 1.0,
            "resource_dependencies": {"resource_b": 1.0},
        },
        "resource_b": {
            "solvent_base_consumption": 1.0,
            "general_base_consumption": 1.0,
            "output_multiplier": 1.0,
            "resource_dependencies": {"resource_a": 1.0},
        },
    }

    with pytest.raises(ValueError, match="Cyclic"):
        calculate_formulaic_consumption(countries, population, formulas, ("resource_a", "resource_b"))

    formulas["resource_b"]["resource_dependencies"] = {"not_in_catalog": 2.0}
    demand = calculate_formulaic_consumption(
        countries,
        population,
        formulas,
        ("resource_a", "resource_b"),
    )
    assert demand is not None
    assert demand.get_column("consumption_usd").is_finite().all()


@pytest.mark.parametrize(
    ("production", "demand"),
    [(float("inf"), 0.0), (0.0, float("nan")), (-1.0, 0.0)],
)
def test_market_rejects_non_finite_and_negative_required_quantities(production, demand):
    with pytest.raises(ValueError, match="finite.*non-negative"):
        _run_market_cycle([("AAA", "cereals", production, demand)], fraction=0.25)


def test_zero_global_market_denominators_produce_no_nan_or_phantom_flows():
    no_supply = _run_market_cycle(
        [("AAA", "cereals", 0.0, 0.0), ("BBB", "cereals", 0.0, 100.0)],
        fraction=0.25,
    )
    no_demand = _run_market_cycle(
        [("AAA", "cereals", 100.0, 0.0), ("BBB", "cereals", 0.0, 0.0)],
        fraction=0.25,
    )

    assert no_supply.get_table("trade_network").is_empty()
    assert no_demand.get_table("trade_network").is_empty()
    assert no_supply.get_table("stockpiles").get_column("stock_amount").is_finite().all()
    assert no_demand.get_table("stockpiles").get_column("stock_amount").is_finite().all()


def test_each_storage_category_applies_its_annual_decay_rate():
    rates = {
        "vehicles": 0.25,
        "pharmaceuticals": 0.15,
        "cereals": 0.10,
        "minerals": 0.02,
        "iron_and_steel": 0.03,
        "precious_stones": 0.0,
    }
    rows = [("AAA", resource, 100.0, 0.0) for resource in rates]
    state = _run_market_cycle(rows, fraction=1.0)
    actual = {
        row["game_resource_id"]: row["stock_amount"]
        for row in state.get_table("stockpiles").iter_rows(named=True)
    }

    assert actual == pytest.approx(
        {resource: 100.0 * (1.0 - rate) for resource, rate in rates.items()}
    )


def test_stockpile_penalty_is_not_applied_at_exactly_fifty_percent_but_applies_above_it():
    at_boundary = _run_market_cycle(
        [("AAA", "precious_stones", 100.0, 50.0)],
        fraction=1.0,
    )
    above_boundary = _run_market_cycle(
        [("AAA", "precious_stones", 100.0, 49.9)],
        fraction=1.0,
    )

    assert at_boundary.get_table("stockpiles").item(0, "stock_amount") == 50.0
    assert at_boundary.get_table("domestic_production").item(0, "domestic_production") == 100.0
    assert above_boundary.get_table("stockpiles").item(0, "stock_amount") == pytest.approx(50.1)
    assert above_boundary.get_table("domestic_production").item(0, "domestic_production") == pytest.approx(97.495)


def test_population_aggregate_cache_tracks_table_identity_and_revision():
    system = InternalEconomySystem()
    first_state = GameState(
        tables={
            "regions": pl.DataFrame(
                {
                    "owner": ["AAA", "AAA"],
                    "pop_14": [10, 5],
                    "pop_15_64": [20, 15],
                    "pop_65": [5, 5],
                }
            )
        }
    )

    first = system._get_population(first_state)
    cached = system._get_population(first_state)
    assert cached is first
    assert first.row(0, named=True) == {"country_id": "AAA", "population": 60}

    first_state.update_table(
        "regions",
        pl.DataFrame(
            {
                "owner": ["AAA"],
                "pop_14": [10],
                "pop_15_64": [20],
                "pop_65": [5],
            }
        ),
    )
    changed = system._get_population(first_state)
    assert changed is not first
    assert changed.row(0, named=True) == {"country_id": "AAA", "population": 35}

    second_state = GameState(
        tables={
            "regions": pl.DataFrame(
                {
                    "owner": ["BBB"],
                    "pop_14": [1],
                    "pop_15_64": [2],
                    "pop_65": [3],
                }
            )
        }
    )
    other_game = system._get_population(second_state)
    assert other_game.row(0, named=True) == {"country_id": "BBB", "population": 6}


def test_aligned_economy_fast_path_matches_polars_path_and_reuses_key_layout():
    resource_ids = tuple(sorted(RESOURCE_MAPPING))

    def make_state() -> tuple[GameState, pl.DataFrame]:
        production_values = [
            float((country_index + 1) * (resource_index + 3))
            for country_index in range(2)
            for resource_index in range(len(resource_ids))
        ]
        return (
            GameState(
                tables={
                    "countries": pl.DataFrame(
                        {
                            "id": ["AAA", "BBB"],
                            "gdp": [1_000_000.0, 2_000_000.0],
                            "gdp_per_capita": [1_000.0, 1_000.0],
                            "money_reserves": [10_000.0, -5_000.0],
                            "internal_tax_rate": [0.2, 0.35],
                            "industrial_growth_rate": [0.025, 0.04],
                        }
                    ),
                    "domestic_production": pl.DataFrame(
                        {
                            "country_id": [country for country in ("AAA", "BBB") for _ in resource_ids],
                            "game_resource_id": list(resource_ids) * 2,
                            "domestic_production": production_values,
                        }
                    ),
                }
            ),
            pl.DataFrame(
                {"country_id": ["AAA", "BBB"], "population": [1_000.0, 2_000.0]}
            ),
        )

    fast_state, population = make_state()
    slow_state, _ = make_state()
    fast_system = InternalEconomySystem()
    slow_system = InternalEconomySystem()
    slow_system._try_process_aligned_economy = lambda state, fraction, aligned_population: False

    reordered_population = pl.DataFrame(
        {"country_id": ["BBB", "AAA"], "population": [2_500.0, 1_500.0]}
    )
    updated_population = pl.DataFrame(
        {"country_id": ["BBB", "AAA"], "population": [3_000.0, 1_750.0]}
    )
    initial_layout = None
    reordered_layout = None
    for index, current_population in enumerate((
        population,
        population,
        reordered_population,
        updated_population,
    )):
        fast_system._process_economy(
            fast_state,
            fraction=0.125,
            population=current_population,
        )
        slow_system._process_economy(
            slow_state,
            fraction=0.125,
            population=current_population,
        )
        current_layout = fast_system._production_layout_cache
        assert current_layout is not None
        if index == 0:
            initial_layout = current_layout
            assert current_layout.population_row_indices.tolist() == [0, 1]
        elif index == 1:
            assert current_layout is initial_layout
        elif index == 2:
            reordered_layout = current_layout
            assert current_layout is not initial_layout
            assert current_layout.population_row_indices.tolist() == [1, 0]
        else:
            assert current_layout is reordered_layout

    population_layout = fast_system._production_layout_cache
    assert population_layout is not None
    assert population_layout.population_ids.equals(
        updated_population.get_column("country_id")
    )
    assert population_layout.population_row_indices.tolist() == [1, 0]

    assert fast_system._production_layout_cache is not None
    fast_countries = fast_state.get_table("countries")
    slow_countries = slow_state.get_table("countries")
    assert set(fast_countries.columns) == set(slow_countries.columns)
    for column in fast_countries.columns:
        fast_values = fast_countries.get_column(column)
        slow_values = slow_countries.get_column(column)
        if fast_values.dtype.is_numeric():
            assert fast_values.to_list() == pytest.approx(
                slow_values.to_list(), rel=1e-12, abs=1e-9
            )
        else:
            assert fast_values.equals(slow_values)

    fast_production = fast_state.get_table("domestic_production")
    slow_production = slow_state.get_table("domestic_production")
    assert fast_production.select("country_id", "game_resource_id").equals(
        slow_production.select("country_id", "game_resource_id")
    )
    assert fast_production.get_column("domestic_production").to_list() == pytest.approx(
        slow_production.get_column("domestic_production").to_list(),
        rel=1e-12,
        abs=1e-9,
    )


def _budget_state(*, gdp: float, human_dev: float, tax_rate: float, reserves: float) -> GameState:
    country = {
        "id": "AAA",
        "gdp": gdp,
        "human_dev": human_dev,
        "personal_income_tax_rate": tax_rate,
        "money_reserves": reserves,
        "interest_rate": 0.05,
        "economic_policy_modifier": 1.0,
        "military_count": 0,
        "corruption_index": 0.0,
        "annual_debt_service": 0.0,
        "budget_imf_ratio": 0.0,
        "trade_income": 0.0,
        "trade_expense": 0.0,
        "security_upkeep": 0.0,
        "diplomacy_upkeep": 0.0,
        "treaty_maintenance": 0.0,
        "diplomatic_aid_expense": 0.0,
    }
    country.update({column: 0.0 for column in BudgetSystem.M_SECTOR})
    return GameState(
        tables={
            "countries": pl.DataFrame([country]),
            "resource_ledger": pl.DataFrame(
                {"country_id": ["AAA"], "consumption_usd": [0.0]}
            ),
            "trade_network": pl.DataFrame(
                {
                    "exporter_id": ["AAA", "WORLD", "AAA"],
                    "importer_id": ["WORLD", "AAA", "WORLD"],
                    "game_resource_id": [
                        "tourism_services",
                        "tourism_services",
                        "cereals",
                    ],
                    "trade_value_usd": [1_000.0, 50_000.0, 5_000.0],
                }
            ),
        }
    )


def test_budget_credits_exact_income_tax_and_foreign_tourism_levy():
    state = _budget_state(gdp=300_000.0, human_dev=0.9, tax_rate=0.3, reserves=100.0)

    BudgetSystem()._process_budget(state, fraction=0.25)

    country = state.tables["countries"].row(0, named=True)
    assert math.isclose(country["revenue_tax"], 27_000.0)
    assert math.isclose(country["tourism_income"], 200.0)
    assert math.isclose(country["total_annual_revenue"], 27_200.0)
    assert math.isclose(country["money_reserves"], 6_900.0)


def test_negative_reserves_accrue_the_configured_five_percent_debt_interest():
    state = _budget_state(gdp=0.0, human_dev=0.9, tax_rate=0.3, reserves=-1_000.0)
    state.update_table(
        "trade_network",
        pl.DataFrame(
            schema={
                "exporter_id": pl.Utf8,
                "importer_id": pl.Utf8,
                "game_resource_id": pl.Utf8,
                "trade_value_usd": pl.Float64,
            }
        ),
    )

    BudgetSystem()._process_budget(state, fraction=0.5)

    country = state.tables["countries"].row(0, named=True)
    assert math.isclose(country["expense_debt_interest"], 50.0)
    assert math.isclose(country["money_reserves"], -1_025.0)


def test_resource_physics_covers_the_shared_catalog_and_service_storage_rules():
    assert set(TradeSystem.RESOURCE_PHYSICS) == set(RESOURCE_MAPPING)
    assert set(InternalEconomySystem.CONSUMPTION_FORMULAS) == set(RESOURCE_MAPPING)
    for resource in (
        "electricity",
        "health_services",
        "transport_services",
        "financial_services",
        "tourism_services",
    ):
        assert TradeSystem.RESOURCE_PHYSICS[resource] == {
            "is_storable": False,
            "decay_rate": 1.0,
        }


def test_unconstrained_market_fast_path_matches_the_dataframe_market():
    def make_state() -> GameState:
        return GameState(
            tables={
                "countries": pl.DataFrame(
                    {
                        "id": ["AAA", "BBB"],
                        "economic_trade_modifier": [1.0, 1.0],
                    }
                ),
                "domestic_production": pl.DataFrame(
                    {
                        "country_id": ["AAA", "BBB"],
                        "game_resource_id": ["cereals", "cereals"],
                        "domestic_production": [100.0, 0.0],
                        "is_gov_controlled": [False, False],
                        "is_legal": [True, True],
                        "tax_rate": [0.05, 0.05],
                    }
                ),
                "resource_ledger": pl.DataFrame(
                    {
                        "country_id": ["AAA", "BBB"],
                        "game_resource_id": ["cereals", "cereals"],
                        "consumption_usd": [50.0, 100.0],
                    }
                ),
            }
        )

    fast_state = make_state()
    slow_state = make_state()
    fast_state.events = [EventRealSecond(game_seconds_passed=1.0, is_paused=False)]
    slow_state.events = list(fast_state.events)

    fast_system = TradeSystem()
    slow_system = TradeSystem()
    slow_system._simulate_market_cycle_fast = lambda state, fraction: False
    fast_system.update(fast_state, 0.0)
    slow_system.update(slow_state, 0.0)

    for table_name in ("countries", "domestic_production", "stockpiles", "trade_network"):
        assert fast_state.get_table(table_name).equals(slow_state.get_table(table_name))


def test_market_fast_path_reuses_and_invalidates_cached_row_indices():
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {"id": ["AAA", "BBB"], "economic_trade_modifier": [1.0, 1.0]}
            ),
            "domestic_production": pl.DataFrame(
                {
                    "country_id": ["AAA", "BBB"],
                    "game_resource_id": ["cereals", "cereals"],
                    "domestic_production": [100.0, 0.0],
                    "is_gov_controlled": [False, False],
                    "is_legal": [True, True],
                    "tax_rate": [0.05, 0.05],
                }
            ),
            "resource_ledger": pl.DataFrame(
                {
                    "country_id": ["AAA", "BBB"],
                    "game_resource_id": ["cereals", "cereals"],
                    "consumption_usd": [50.0, 100.0],
                }
            ),
        }
    )
    system = TradeSystem()

    assert system._simulate_market_cycle_fast(state, 0.25)
    first_cache = system._market_index_cache
    assert first_cache is not None
    assert system._simulate_market_cycle_fast(state, 0.25)
    assert system._market_index_cache is first_cache

    state.update_table("countries", state.get_table("countries").reverse())
    assert system._simulate_market_cycle_fast(state, 0.25)
    rebuilt_cache = system._market_index_cache
    assert rebuilt_cache is not None and rebuilt_cache is not first_cache
    assert rebuilt_cache.country_indices.tolist() == [1, 0]


def test_market_fast_path_caches_indices_in_canonical_output_order():
    def make_state() -> GameState:
        rows = [
            ("AAA", "vehicles", 100.0, 20.0),
            ("AAA", "cereals", 80.0, 10.0),
            ("BBB", "vehicles", 40.0, 90.0),
            ("BBB", "cereals", 20.0, 75.0),
        ]
        return GameState(
            tables={
                "countries": pl.DataFrame(
                    {"id": ["AAA", "BBB"], "economic_trade_modifier": [1.0, 1.0]}
                ),
                "domestic_production": pl.DataFrame(
                    {
                        "country_id": [row[0] for row in rows],
                        "game_resource_id": [row[1] for row in rows],
                        "domestic_production": [row[2] for row in rows],
                        "is_gov_controlled": [False] * len(rows),
                        "is_legal": [True] * len(rows),
                        "tax_rate": [0.05] * len(rows),
                    }
                ),
                "resource_ledger": pl.DataFrame(
                    {
                        "country_id": [row[0] for row in rows],
                        "game_resource_id": [row[1] for row in rows],
                        "consumption_usd": [row[3] for row in rows],
                    }
                ),
            }
        )

    fast_state = make_state()
    slow_state = make_state()
    fast_system = TradeSystem()
    slow_system = TradeSystem()
    slow_system._simulate_market_cycle_fast = lambda state, fraction: False

    assert fast_system._simulate_market_cycle_fast(fast_state, 0.25)
    slow_system._simulate_market_cycle(slow_state, 0.25)
    for table_name in ("countries", "domestic_production", "stockpiles", "trade_network"):
        assert fast_state.get_table(table_name).equals(slow_state.get_table(table_name))

    fast_production = fast_state.get_table("domestic_production")
    cached_indices = fast_system._market_index_cache
    assert cached_indices is not None
    assert cached_indices.keys_are_sorted
    assert cached_indices.production_country_ids.equals(
        fast_production.get_column("country_id")
    )
    assert cached_indices.production_resource_ids.equals(
        fast_production.get_column("game_resource_id")
    )
    resource_index = {
        resource_id: index
        for index, (resource_id, _is_storable, _decay_rate)
        in enumerate(cached_indices.physics_entries)
    }
    expected_resources = fast_production.get_column("game_resource_id").to_list()
    assert cached_indices.resource_indices.tolist() == [
        resource_index[resource_id] for resource_id in expected_resources
    ]

    for state in (fast_state, slow_state):
        state.update_table(
            "resource_ledger",
            state.get_table("resource_ledger").sort("country_id", "game_resource_id"),
        )
    assert fast_system._simulate_market_cycle_fast(fast_state, 0.25)
    slow_system._simulate_market_cycle(slow_state, 0.25)
    assert fast_system._market_index_cache is cached_indices

    for table_name in ("countries", "domestic_production", "stockpiles", "trade_network"):
        assert fast_state.get_table(table_name).equals(slow_state.get_table(table_name))


def _run_market_cycle(
    rows: list[tuple[str, str, float, float]],
    *,
    fraction: float,
) -> GameState:
    country_ids = sorted({row[0] for row in rows})
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": country_ids,
                    "economic_trade_modifier": [1.0] * len(country_ids),
                }
            ),
            "domestic_production": pl.DataFrame(
                {
                    "country_id": [row[0] for row in rows],
                    "game_resource_id": [row[1] for row in rows],
                    "domestic_production": [row[2] for row in rows],
                    "is_gov_controlled": [False] * len(rows),
                    "is_legal": [True] * len(rows),
                    "tax_rate": [0.05] * len(rows),
                }
            ),
            "resource_ledger": pl.DataFrame(
                {
                    "country_id": [row[0] for row in rows],
                    "game_resource_id": [row[1] for row in rows],
                    "consumption_usd": [row[3] for row in rows],
                }
            ),
        }
    )

    TradeSystem()._simulate_market_cycle(state, fraction)
    return state


def test_global_market_clearing_caps_exports_and_imports_by_world_ratios():
    state = _run_market_cycle(
        [
            ("AAA", "cereals", 200.0, 0.0),
            ("BBB", "cereals", 0.0, 100.0),
        ],
        fraction=0.25,
    )

    flows = state.get_table("trade_network").sort("exporter_id", "importer_id")
    assert flows.select("exporter_id", "importer_id", "trade_value_usd").rows() == [
        ("AAA", "WORLD", 100.0),
        ("WORLD", "BBB", 100.0),
    ]
    assert state.get_table("stockpiles").filter(
        pl.col("country_id") == "AAA"
    ).item(0, "stock_amount") == 97.5


def test_unsold_service_stock_evaporates_and_applies_the_half_capacity_penalty():
    state = _run_market_cycle(
        [("AAA", "tourism_services", 100.0, 0.0)],
        fraction=1.0,
    )

    assert state.get_table("stockpiles").item(0, "stock_amount") == 0.0
    assert state.get_table("domestic_production").item(0, "domestic_production") == 50.0


def test_unsold_steel_decays_by_elapsed_year_fraction_and_penalizes_excess_storage():
    state = _run_market_cycle(
        [("AAA", "iron_and_steel", 100.0, 0.0)],
        fraction=0.5,
    )

    assert math.isclose(
        state.get_table("stockpiles").item(0, "stock_amount"),
        98.5,
    )
    assert math.isclose(
        state.get_table("domestic_production").item(0, "domestic_production"),
        97.5375,
    )


def test_budget_applies_specified_military_upkeep_per_country():
    state = _budget_state(gdp=0.0, human_dev=0.8, tax_rate=0.0, reserves=0.0)
    state.update_table(
        "countries",
        state.get_table("countries").with_columns(pl.lit(2).alias("military_count")),
    )
    state.update_table(
        "trade_network",
        pl.DataFrame(
            schema={
                "exporter_id": pl.Utf8,
                "importer_id": pl.Utf8,
                "game_resource_id": pl.Utf8,
                "trade_value_usd": pl.Float64,
            }
        ),
    )

    BudgetSystem()._process_budget(state, fraction=1.0)

    country = state.get_table("countries").row(0, named=True)
    assert country["expense_military_upkeep"] == 800_000.0
    assert country["money_reserves"] == -800_000.0


def test_repeated_budget_ticks_have_no_reserve_drift_and_zero_balance_has_no_interest():
    state = _budget_state(gdp=300_000.0, human_dev=0.9, tax_rate=0.3, reserves=100.0)
    state.update_table(
        "trade_network",
        pl.DataFrame(
            schema={
                "exporter_id": pl.Utf8,
                "importer_id": pl.Utf8,
                "game_resource_id": pl.Utf8,
                "trade_value_usd": pl.Float64,
            }
        ),
    )
    budget = BudgetSystem()

    for _ in range(100):
        budget._process_budget(state, fraction=0.25)

    country = state.get_table("countries").row(0, named=True)
    assert country["money_reserves"] == 675_100.0
    assert country["expense_debt_interest"] == 0.0

    zero_balance = _budget_state(gdp=0.0, human_dev=0.5, tax_rate=0.0, reserves=0.0)
    zero_balance.update_table("trade_network", pl.DataFrame(schema=state.get_table("trade_network").schema))
    budget._process_budget(zero_balance, fraction=1.0)
    assert zero_balance.get_table("countries").item(0, "expense_debt_interest") == 0.0


def test_dense_budget_fast_path_matches_polars_fallback_and_reuses_ledger_layout():
    resource_ids = tuple(sorted(RESOURCE_MAPPING))

    def make_state() -> GameState:
        return GameState(
            tables={
                "countries": pl.DataFrame(
                    {
                        "id": ["AAA", "BBB"],
                        "gdp": [2_500_000.0, 1_250_000.0],
                        "human_dev": [0.82, 0.61],
                        "personal_income_tax_rate": [0.31, 0.22],
                        "economic_policy_modifier": [0.9, 0.75],
                        "money_reserves": [-12_500.0, 45_000.0],
                        "interest_rate": [0.04, 0.05],
                        "trade_income": [2_300.0, 450.0],
                        "trade_expense": [900.0, 110.0],
                        "budget_edu_ratio": [0.6, 0.4],
                        "budget_health_ratio": [0.7, 0.3],
                        "budget_social_ratio": [0.5, 0.2],
                        "budget_env_ratio": [0.4, 0.3],
                        "budget_gov_ratio": [0.2, 0.4],
                        "budget_infra_ratio": [0.5, 0.35],
                        "budget_telecom_ratio": [0.3, 0.2],
                        "budget_research_ratio": [0.25, 0.1],
                        "budget_imf_ratio": [500.0, 0.0],
                        "corruption_index": [0.08, 0.15],
                        "military_count": [1, 0],
                        "annual_debt_service": [1_000.0, 0.0],
                    }
                ),
                "resource_ledger": pl.DataFrame(
                    {
                        "country_id": [country for country in ("AAA", "BBB") for _ in resource_ids],
                        "game_resource_id": list(resource_ids) * 2,
                        "consumption_usd": [
                            float((country_index + 1) * (resource_index + 1)) / 7.0
                            for country_index in range(2)
                            for resource_index in range(len(resource_ids))
                        ],
                    }
                ),
                "trade_network": pl.DataFrame(
                    {
                        "exporter_id": ["AAA", "WORLD", "BBB"],
                        "importer_id": ["WORLD", "AAA", "WORLD"],
                        "game_resource_id": [
                            "tourism_services",
                            "tourism_services",
                            "cereals",
                        ],
                        "trade_value_usd": [12_000.0, 4_000.0, 500.0],
                    }
                ),
            }
        )

    fast_state = make_state()
    slow_state = make_state()
    fast_system = BudgetSystem()
    slow_system = BudgetSystem()
    slow_system._try_process_budget_fast = lambda state, fraction: False

    fast_system._process_budget(fast_state, fraction=0.125)
    slow_system._process_budget(slow_state, fraction=0.125)
    first_layout = fast_system._dense_demand_layout_cache
    fast_system._process_budget(fast_state, fraction=0.125)
    slow_system._process_budget(slow_state, fraction=0.125)

    assert first_layout is not None
    assert fast_system._dense_demand_layout_cache is first_layout
    fast_countries = fast_state.get_table("countries")
    slow_countries = slow_state.get_table("countries")
    assert set(fast_countries.columns) == set(slow_countries.columns)
    for column in fast_countries.columns:
        fast_values = fast_countries.get_column(column)
        slow_values = slow_countries.get_column(column)
        if fast_values.dtype.is_numeric():
            assert fast_values.to_list() == pytest.approx(
                slow_values.to_list(), rel=1e-12, abs=1e-9
            )
        else:
            assert fast_values.equals(slow_values)


def test_stable_group_sum_uses_a_fast_unique_path_and_exact_duplicate_reduction():
    unique = pl.DataFrame(
        {
            "country_id": ["AAA", "BBB"],
            "amount": [1, 2],
        }
    )
    unique_result = stable_group_sum(
        unique,
        ("country_id",),
        "amount",
        "total",
    )
    assert unique_result.schema["total"] == pl.Float64
    assert unique_result["total"].to_list() == [1.0, 2.0]

    duplicate = pl.DataFrame(
        {
            "country_id": ["AAA", "AAA", "AAA", "BBB"],
            "amount": [1e16, 1.0, -1e16, None],
        }
    )
    duplicate_result = stable_group_sum(
        duplicate,
        ("country_id",),
        "amount",
        "total",
    ).sort("country_id")
    assert duplicate_result["total"].to_list() == [1.0, 0.0]


def test_stable_group_sums_batches_multiple_exact_reductions_per_key():
    values = pl.DataFrame(
        {
            "country_id": ["AAA", "AAA", "AAA", "BBB"],
            "revenue": [1e16, 1.0, -1e16, 2.0],
            "expense": [1.0, 1e16, -1e16, None],
        }
    )

    result = stable_group_sums(
        values,
        ("country_id",),
        {"revenue": "total_revenue", "expense": "total_expense"},
    ).sort("country_id")

    assert result.schema == {
        "country_id": pl.Utf8,
        "total_revenue": pl.Float64,
        "total_expense": pl.Float64,
    }
    assert result["total_revenue"].to_list() == [1.0, 2.0]
    assert result["total_expense"].to_list() == [1.0, 0.0]


def test_stable_group_sums_preserves_multiple_keys_and_null_semantics():
    values = pl.DataFrame(
        {
            "country_id": ["AAA", "AAA", "AAA", "AAA", "BBB", "BBB"],
            "region_id": [1, 1, 1, 2, 1, 2],
            "revenue": [1e16, 1.0, -1e16, 12.0, None, 6.0],
            "expense": [1.0, None, 0.0, 5.0, 7.0, 8.0],
        }
    )

    result = stable_group_sums(
        values,
        ("country_id", "region_id"),
        {"revenue": "total_revenue", "expense": "total_expense"},
    ).sort("country_id", "region_id")

    assert result.select("country_id", "region_id").rows() == [
        ("AAA", 1),
        ("AAA", 2),
        ("BBB", 1),
        ("BBB", 2),
    ]
    assert result["total_revenue"].to_list() == [1.0, 12.0, 0.0, 6.0]
    assert result["total_expense"].to_list() == [1.0, 5.0, 7.0, 8.0]


def test_dense_nonnegative_row_reduction_uses_reproducible_edge_fallback():
    values = np.asarray([[1.25, 2.5, 3.75], [1e16, 1.0, -1e16]])

    assert stable_nonnegative_row_totals(values).tolist() == [7.5, 1.0]


def test_ensure_sorted_orders_unsorted_rows_and_preserves_existing_order():
    unsorted = pl.DataFrame({"country_id": ["BBB", "AAA"], "value": [2, 1]})

    ordered = ensure_sorted(unsorted, ("country_id",))

    assert ordered["country_id"].to_list() == ["AAA", "BBB"]
    assert ensure_sorted(ordered, ("country_id",)) is ordered
