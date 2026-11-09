from __future__ import annotations

import polars as pl
import pytest

from modules.base.systems.economy import aligned_economy_fast_path
from modules.base.systems.economy import internal_economy_system as economy_module
from modules.base.systems.economy.internal_economy_system import (
    InternalEconomySystem,
)
from src.shared.actions import (
    ActionIncreaseResourceProduction,
    ActionUpdateResourcePolicy,
)
from src.shared.state import GameState


def _state() -> GameState:
    return GameState(
        tables={
            "countries": pl.DataFrame(
                {"id": ["AAA"], "money_reserves": [1000.0]}
            ),
            "domestic_production": pl.DataFrame(
                {
                    "country_id": ["AAA"],
                    "game_resource_id": ["fossil_fuels"],
                    "domestic_production": [100.0],
                }
            ),
        },
        globals={"player_country_map": {"player": "AAA"}},
    )


def _production_action(**changes) -> ActionIncreaseResourceProduction:
    values = {
        "player_id": "player",
        "country_tag": "AAA",
        "resource_id": "fossil_fuels",
        "increase_percent": 25,
    }
    values.update(changes)
    return ActionIncreaseResourceProduction(**values)


def _policy_action(**changes) -> ActionUpdateResourcePolicy:
    values = {
        "player_id": "player",
        "country_tag": "AAA",
        "resource_id": "fossil_fuels",
        "is_gov_controlled": True,
        "is_legal": False,
        "tax_rate": 0.25,
    }
    values.update(changes)
    return ActionUpdateResourcePolicy(**values)


def _validate_production(state, action) -> str:
    country = str(action.country_tag or "").strip().upper()
    resource = str(action.resource_id or "").strip().lower()
    return InternalEconomySystem._validate_production_increase_action(
        state, action, country, resource
    )


def _validate_policy(state, action) -> str:
    country = str(action.country_tag or "").strip().upper()
    resource = str(action.resource_id or "").strip().lower()
    return InternalEconomySystem._validate_resource_policy_action(
        state, action, country, resource
    )


def test_production_validation_rejects_invalid_identity_and_action_values() -> None:
    state = _state()
    assert "Select a country" in _validate_production(
        state, _production_action(country_tag="")
    )

    state = _state()
    state.tables["countries"] = pl.DataFrame({"id": ["AAA"]})
    assert "treasury data is unavailable" in _validate_production(
        state, _production_action()
    )

    state = _state()
    state.tables["countries"] = pl.DataFrame(
        {"id": ["AAA", " aaa "], "money_reserves": [1000.0, 1000.0]}
    )
    assert "unavailable or ambiguous" in _validate_production(
        state, _production_action()
    )

    state = _state()
    assert "resource is unavailable" in _validate_production(
        state, _production_action(resource_id="unknown")
    )
    assert "supported production increase" in _validate_production(
        state, _production_action(increase_percent=True)
    )


@pytest.mark.parametrize("reserves", ["invalid", None, float("inf")])
def test_production_validation_rejects_invalid_treasury_values(reserves) -> None:
    state = _state()
    if reserves is None:
        state.tables["countries"] = pl.DataFrame(
            {
                "id": ["AAA"],
                "money_reserves": pl.Series([None], dtype=pl.Float64),
            }
        )
    else:
        state.tables["countries"] = pl.DataFrame(
            {"id": ["AAA"], "money_reserves": [reserves]}
        )

    assert "treasury data is unavailable" in _validate_production(
        state, _production_action()
    )


def test_production_validation_rejects_missing_and_ambiguous_production_rows() -> None:
    state = _state()
    state.tables["domestic_production"] = pl.DataFrame(
        {"country_id": ["AAA"], "game_resource_id": ["fossil_fuels"]}
    )
    assert "production data is unavailable" in _validate_production(
        state, _production_action()
    )

    state = _state()
    row = state.tables["domestic_production"]
    state.tables["domestic_production"] = pl.concat([row, row])
    assert "row is missing or ambiguous" in _validate_production(
        state, _production_action()
    )


def test_resource_policy_validation_rejects_missing_identity_and_policy_data() -> None:
    state = _state()
    assert "Select a country" in _validate_policy(
        state, _policy_action(country_tag="")
    )

    state = _state()
    state.tables["countries"] = pl.DataFrame({"name": ["AAA"]})
    assert "country is unavailable" in _validate_policy(state, _policy_action())

    state = _state()
    assert "resource is unavailable" in _validate_policy(
        state, _policy_action(resource_id="unknown")
    )
    assert "must be boolean" in _validate_policy(
        state, _policy_action(is_gov_controlled=1)
    )
    assert "finite ratio" in _validate_policy(
        state, _policy_action(tax_rate="invalid")
    )

    state = _state()
    state.tables["domestic_production"] = pl.DataFrame(
        {"country_id": ["AAA"]}
    )
    assert "policy data is unavailable" in _validate_policy(
        state, _policy_action()
    )

    state = _state()
    row = state.tables["domestic_production"]
    state.tables["domestic_production"] = pl.concat([row, row])
    assert "row is missing or ambiguous" in _validate_policy(
        state, _policy_action()
    )


def test_resource_policy_handler_adds_legacy_columns_before_applying_values() -> None:
    state = _state()
    state.tables["domestic_production"] = pl.DataFrame(
        {
            "country_id": ["AAA", "BBB"],
            "game_resource_id": ["fossil_fuels", "fossil_fuels"],
            "domestic_production": [100.0, 50.0],
        }
    )

    InternalEconomySystem()._handle_update_resource_policy(
        state, _policy_action()
    )

    production = state.tables["domestic_production"].sort("country_id")
    target = production.filter(pl.col("country_id") == "AAA").row(
        0, named=True
    )
    untouched = production.filter(pl.col("country_id") == "BBB").row(
        0, named=True
    )
    assert target["is_gov_controlled"] is True
    assert target["is_legal"] is False
    assert target["tax_rate"] == 0.25
    assert untouched["is_gov_controlled"] is False
    assert untouched["is_legal"] is True
    assert untouched["tax_rate"] == 0.0


def _formulaic_state() -> GameState:
    return GameState(
        tables={
            "countries": pl.DataFrame(
                {"id": ["AAA"], "gdp": [1_000_000.0]}
            ),
            "regions": pl.DataFrame(
                {
                    "owner": ["AAA"],
                    "pop_14": [100.0],
                    "pop_15_64": [700.0],
                    "pop_65": [200.0],
                }
            ),
        }
    )


def test_formulaic_consumption_uses_legacy_defaults_when_fast_path_declines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        economy_module, "calculate_formulaic_consumption_fast", lambda *_args: None
    )

    result = InternalEconomySystem()._calculate_formulaic_consumption(
        _formulaic_state()
    )

    assert result.height == len(economy_module._CONSUMPTION_CALC_ORDER)
    assert set(result.columns) == {
        "country_id",
        "game_resource_id",
        "consumption_usd",
    }
    assert result["consumption_usd"].is_finite().all()


def test_formulaic_consumption_reports_cyclic_resource_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        economy_module, "calculate_formulaic_consumption_fast", lambda *_args: None
    )
    formulas = {
        resource: dict(formula)
        for resource, formula in InternalEconomySystem.CONSUMPTION_FORMULAS.items()
    }
    first, second = economy_module._CONSUMPTION_CALC_ORDER[:2]
    formulas[first]["resource_dependencies"] = {second: 1.0}
    formulas[second]["resource_dependencies"] = {first: 1.0}
    monkeypatch.setattr(InternalEconomySystem, "CONSUMPTION_FORMULAS", formulas)

    with pytest.raises(ValueError, match="Cyclic resource demand dependencies"):
        InternalEconomySystem()._calculate_formulaic_consumption(_formulaic_state())


def _dense_economy_frames():
    resource_ids = list(aligned_economy_fast_path._RESOURCE_ORDER)
    countries = pl.DataFrame(
        {"id": ["AAA"], "money_reserves": [1000.0]}
    )
    production = pl.DataFrame(
        {
            "country_id": ["AAA"] * len(resource_ids),
            "game_resource_id": resource_ids,
            "domestic_production": [10.0] * len(resource_ids),
        }
    )
    population = pl.DataFrame(
        {"country_id": ["AAA"], "population": [1000.0]}
    )
    consumption = pl.DataFrame(
        {
            "country_id": ["AAA"] * len(resource_ids),
            "game_resource_id": resource_ids,
            "consumption_usd": [3.0] * len(resource_ids),
        }
    )
    return countries, production, population, consumption


def test_no_trade_ledger_uses_cached_and_uncached_aligned_rows() -> None:
    countries, production, population, consumption = _dense_economy_frames()
    aligned = aligned_economy_fast_path.update_aligned_economy_tables(
        countries, production, population, 0.5, None
    )
    assert aligned is not None

    cached_system = InternalEconomySystem()
    cached_system._production_layout_cache = aligned.layout_cache
    cached_ledger = cached_system._build_resource_ledger_without_trade(
        production, None, consumption
    )
    assert cached_ledger is not None
    assert cached_ledger["balance_usd"].to_list() == [7.0] * production.height

    uncached_ledger = InternalEconomySystem()._build_resource_ledger_without_trade(
        production, None, consumption
    )
    assert uncached_ledger is not None
    assert uncached_ledger["trade_usd"].to_list() == [0.0] * production.height

    mismatched = consumption.with_columns(pl.lit("BBB").alias("country_id"))
    assert (
        InternalEconomySystem()._build_resource_ledger_without_trade(
            production, None, mismatched
        )
        is None
    )

    duplicated_production = pl.concat([production, production.head(1)])
    duplicated_consumption = pl.concat([consumption, consumption.head(1)])
    assert (
        InternalEconomySystem()._build_resource_ledger_without_trade(
            duplicated_production, None, duplicated_consumption
        )
        is None
    )


def test_resource_ledger_builder_publishes_the_no_trade_fast_path() -> None:
    state = _state()
    consumption = pl.DataFrame(
        {
            "country_id": ["AAA"],
            "game_resource_id": ["fossil_fuels"],
            "consumption_usd": [25.0],
        }
    )
    system = InternalEconomySystem()
    system._calculate_formulaic_consumption = lambda *_args: consumption

    system._build_resource_ledger(state)

    ledger = state.tables["resource_ledger"].row(0, named=True)
    assert ledger["production_usd"] == 100.0
    assert ledger["consumption_usd"] == 25.0
    assert ledger["balance_usd"] == 75.0


def test_economy_processing_returns_when_required_tables_are_missing() -> None:
    InternalEconomySystem()._process_economy(GameState(), 0.25)


def test_aligned_economy_handles_missing_regions_and_default_columns() -> None:
    countries, production, _population, _consumption = _dense_economy_frames()
    no_regions = GameState(
        tables={"countries": countries, "domestic_production": production}
    )
    assert (
        InternalEconomySystem()._try_process_aligned_economy(
            no_regions, 0.25, None
        )
        is False
    )

    state = GameState(
        tables={
            "countries": countries,
            "domestic_production": production,
            "regions": pl.DataFrame(
                {
                    "owner": ["AAA"],
                    "pop_14": [100.0],
                    "pop_15_64": [700.0],
                    "pop_65": [200.0],
                }
            ),
        }
    )
    system = InternalEconomySystem()
    assert system._try_process_aligned_economy(state, 0.25, None) is True
    assert state.tables["countries"]["gdp"][0] > 0.0
    assert "internal_tax_rate" in state.tables["countries"].columns


def test_aligned_economy_falls_back_when_population_schema_is_invalid() -> None:
    countries, production, _population, _consumption = _dense_economy_frames()
    state = GameState(
        tables={"countries": countries, "domestic_production": production}
    )
    invalid_population = pl.DataFrame(
        {"country_id": ["AAA"], "population": ["not numeric"]}
    )

    assert (
        InternalEconomySystem()._try_process_aligned_economy(
            state, 0.25, invalid_population
        )
        is False
    )
