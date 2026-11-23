from pathlib import Path

import polars as pl
import pytest

from src.server.io.data_load_manager import DataLoader
from src.server.io.static_loader import StaticAssetLoader
from src.shared.config import GameConfig
from src.shared.resource_production_policy import production_increase_basis
from src.shared.state import GameState


@pytest.fixture(scope="module")
def resource_data():
    config = GameConfig(Path(__file__).resolve().parents[1])
    static_loader = StaticAssetLoader(config)
    loader = DataLoader(config)
    regions = static_loader._load_regions()
    return (
        static_loader._load_countries(),
        regions,
        loader._load_domestic_production(),
        loader._load_regional_production(regions),
    )


def test_world_resource_allocations_reconcile_with_2001_gdp(resource_data):
    countries, regions, national, regional = resource_data
    owner_by_region = dict(regions.select("id", "owner").iter_rows())
    national_totals = {
        (country, resource): amount
        for country, resource, amount in national.select(
            "country_id", "game_resource_id", "domestic_production"
        ).iter_rows()
    }
    regional_totals = {
        (country, resource): amount
        for country, resource, amount in regional.group_by(
            "country_id", "game_resource_id"
        ).agg(pl.col("domestic_production").sum()).iter_rows()
    }
    assert regional["id"].n_unique() == regional.height
    assert all(
        owner_by_region[region] == country
        for country, region in regional.select("country_id", "region_id").iter_rows()
    )
    assert regional_totals == {key: amount for key, amount in national_totals.items() if amount > 0}

    primary = "historical_gdp_current_usd_2001"
    supplement = "historical_gdp_snaama_current_usd_2001"
    proxy = f"{primary}_gameplay_proxy"
    gdp_by_country = {
        row["id"]: round(row[primary]) if row[f"{primary}_available"] else
        round(row[supplement]) if row[f"{supplement}_available"] else
        round(row[f"{proxy}_value"]) if row[f"{proxy}_available"] else 0
        for row in countries.iter_rows(named=True)
    }
    for country, amount in national.group_by("country_id").agg(
        pl.col("domestic_production").sum()
    ).iter_rows():
        assert amount == gdp_by_country[country], country


@pytest.mark.parametrize("country", ["UKR", "POL", "DEU", "FRA", "GBR", "RUS", "USA", "CHN"])
def test_production_increases_use_reconciled_regional_base(resource_data, country):
    _, regions, national, regional = resource_data
    state = GameState(tables={
        "regions": regions,
        "domestic_production": national,
        "regional_production": regional,
    })
    for resource in ("cereals", "fossil_fuels", "iron_and_steel"):
        amount = national.filter(
            (pl.col("country_id") == country) & (pl.col("game_resource_id") == resource)
        )["domestic_production"][0]
        basis = production_increase_basis(state, country, resource)
        assert basis is not None and basis.source == "regional"
        assert basis.annual_value_usd == amount
