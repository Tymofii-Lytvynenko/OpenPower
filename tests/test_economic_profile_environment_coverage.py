import polars as pl

from modules.base.systems.economy.economic_profile_environment import (
    DeterministicEconomicProfileEnvironmentCalculator,
    EconomicProfileEnvironmentInputs,
    _finite_number,
)


def test_labor_supply_is_empty_when_region_schema_lacks_working_age_population():
    inputs = EconomicProfileEnvironmentInputs(
        now=0,
        random_event_effects=None,
        regions=pl.DataFrame({"owner": ["AAA"]}),
        resource_ledger=None,
    )

    environment = DeterministicEconomicProfileEnvironmentCalculator().calculate(inputs)

    assert environment.labor_by_country == {}


def test_finite_number_uses_default_for_unparseable_values():
    assert _finite_number("not-a-number", default=7.5) == 7.5
    assert _finite_number(None, default=3.0) == 3.0
