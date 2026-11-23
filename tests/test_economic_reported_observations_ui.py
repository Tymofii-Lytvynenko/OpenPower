import polars as pl

from src.client.ui.panels.historical_economic_baseline import (
    historical_economic_tooltip,
)
from src.server.io.static_loader import StaticAssetLoader
from src.shared.config import GameConfig
from utils.import_economic_indicators_2001 import ROOT


def _country_row(countries, country_id):
    return countries.filter(pl.col("id") == country_id)


def test_snaama_gdp_supplement_is_visible_alongside_the_missing_wdi_baseline():
    countries = StaticAssetLoader(GameConfig(ROOT))._load_countries()
    row = _country_row(countries, "PRK")

    tooltip = historical_economic_tooltip(
        row,
        "historical_gdp_current_usd_2001",
        "$ 20 000 000",
        "GDP",
        value_formatter=lambda value: f"$ {value:,.0f}",
    )

    assert "Current simulated GDP: $ 20 000 000" in tooltip
    assert "2001 baseline (GDP (current US$)): $ 18,000,000,000" in tooltip
    assert "Alternative historical observation (UNdata SNAAMA GDP estimate" in tooltip
    assert "$ 11,021,860,465" in tooltip
    assert "Observation period: 2001; source observation year: 2001" in tooltip
    assert "not WDI" in tooltip
    assert "https://data.un.org/Data.aspx?d=SNAAMA" in tooltip

    per_capita_tooltip = historical_economic_tooltip(
        row,
        "historical_gdp_per_capita_current_usd_2001",
        "$ 500",
        "GDP per capita",
        value_formatter=lambda value: f"$ {value:,.0f}",
    )
    assert (
        "Alternative historical observation (UNdata SNAAMA GDP per capita estimate"
        in per_capita_tooltip
    )
    assert "$ 476" in per_capita_tooltip


def test_manual_country_value_fills_missing_inflation_baseline():
    countries = StaticAssetLoader(GameConfig(ROOT))._load_countries()
    row = _country_row(countries, "PRK")

    tooltip = historical_economic_tooltip(
        row,
        "historical_inflation_cpi_pct_2001",
        "1.0%",
        "inflation rate",
        value_formatter=lambda value: f"{value:.2f}%",
    )

    assert "2001 baseline (Inflation, consumer prices (annual %)): 10.00%." in tooltip
    assert "Gameplay proxy" not in tooltip


def test_manual_country_value_fills_missing_unemployment_baseline():
    countries = StaticAssetLoader(GameConfig(ROOT))._load_countries()
    row = _country_row(countries, "AND")

    tooltip = historical_economic_tooltip(
        row,
        "historical_unemployment_modeled_ilo_pct_2001",
        "2.0%",
        "unemployment rate",
        value_formatter=lambda value: f"{value:.1f}%",
    )

    assert "2001 baseline (Unemployment, modeled ILO estimate (% of labor force)): 2.0%." in tooltip
    assert "Gameplay proxy" not in tooltip


def test_antarctica_country_baseline_displays_zero():
    countries = StaticAssetLoader(GameConfig(ROOT))._load_countries()
    row = _country_row(countries, "ATA")

    tooltip = historical_economic_tooltip(
        row,
        "historical_gdp_current_usd_2001",
        "unavailable",
        "GDP",
    )

    assert "2001 baseline (GDP (current US$)): 0." in tooltip


def test_existing_reported_cpi_supplement_is_visible_in_the_inflation_tooltip():
    countries = StaticAssetLoader(GameConfig(ROOT))._load_countries()
    row = _country_row(countries, "AND")

    tooltip = historical_economic_tooltip(
        row,
        "historical_inflation_cpi_pct_2001",
        "1.0%",
        "inflation rate",
        value_formatter=lambda value: f"{value:.1f}%",
    )

    assert "Alternative historical observation (Reported CPI inflation" in tooltip
    assert "2.77 %/year" in tooltip
    assert "Government of Andorra" in tooltip
    assert "BOPA issue 4" in tooltip


def test_staff_cpi_estimate_is_visible_as_a_separate_annual_average_series():
    countries = StaticAssetLoader(GameConfig(ROOT))._load_countries()
    row = _country_row(countries, "SMR")

    tooltip = historical_economic_tooltip(
        row,
        "historical_inflation_cpi_pct_2001",
        "2.0%",
        "inflation rate",
        value_formatter=lambda value: f"{value:.1f}%",
    )

    assert (
        "Alternative historical observation (IMF staff annual-average CPI estimate"
        in tooltip
    )
    assert "3.3 % annual average" in tooltip
    assert "Observation period: calendar year 2001" in tooltip
    assert "as a staff estimate" in tooltip


def test_reported_cpi_supplements_are_visible_with_period_and_source_scope():
    countries = StaticAssetLoader(GameConfig(ROOT))._load_countries()
    row = _country_row(countries, "CUB")

    tooltip = historical_economic_tooltip(
        row,
        "historical_inflation_cpi_pct_2001",
        "1.2%",
        "inflation rate",
        value_formatter=lambda value: f"{value:.1f}%",
    )

    assert "Current simulated inflation rate: 1.2%" in tooltip
    assert "Alternative historical observation (Reported CPI inflation" in tooltip
    assert "-0.5 % December-to-December" in tooltip
    assert "Observation period: 2001" in tooltip
    assert "local-currency markets" in tooltip
    assert (
        "https://repositorio.cepal.org/bitstream/11362/958/1/S0211936_en.pdf" in tooltip
    )


def test_fiscal_year_cpi_alternative_discloses_kabul_scope_and_observation_period():
    countries = StaticAssetLoader(GameConfig(ROOT))._load_countries()
    row = _country_row(countries, "AFG")

    tooltip = historical_economic_tooltip(
        row,
        "historical_inflation_cpi_pct_2001",
        "4.0%",
        "inflation rate",
        value_formatter=lambda value: f"{value:.1f}%",
    )

    assert "Alternative historical observation (IMF Kabul CPI estimate" in tooltip
    assert "-43.4 % year-on-year" in tooltip
    assert "Observation period: Afghan fiscal year 2001/02" in tooltip
    assert "not a calendar-year national CPI" in tooltip
    assert (
        "https://www.elibrary.imf.org/view/journals/002/2005/033/article-A003-en.xml"
        in tooltip
    )


def test_reported_unemployment_supplement_is_shown_even_when_ilo_is_available():
    countries = StaticAssetLoader(GameConfig(ROOT))._load_countries()
    row = _country_row(countries, "CUB")

    tooltip = historical_economic_tooltip(
        row,
        "historical_unemployment_modeled_ilo_pct_2001",
        "3.8%",
        "unemployment rate",
        value_formatter=lambda value: f"{value:.1f}%",
    )

    assert "2001 historical baseline (Unemployment, modeled ILO estimate" in tooltip
    assert "Alternative historical observation (Reported unemployment rate" in tooltip
    assert "4.1 % of labor force, urban" in tooltip
    assert "urban only" in tooltip
    assert (
        "https://repositorio.cepal.org/bitstream/11362/958/1/S0211936_en.pdf" in tooltip
    )


def test_adjacent_year_census_observation_keeps_its_real_year_and_scope():
    countries = StaticAssetLoader(GameConfig(ROOT))._load_countries()
    row = _country_row(countries, "TUV")

    tooltip = historical_economic_tooltip(
        row,
        "historical_unemployment_modeled_ilo_pct_2001",
        "2.0%",
        "unemployment rate",
        value_formatter=lambda value: f"{value:.1f}%",
    )

    assert (
        "Alternative historical observation (Reported unemployment rate (2002 census))"
        in tooltip
    )
    assert "6.5 % of labour force, residents aged 15+" in tooltip
    assert (
        "Observation period: 2002 population census; source observation year: 2002"
        in tooltip
    )
    assert "scenario year: 2001" in tooltip
    assert (
        "https://www.fao.org/fileadmin/templates/ess/ess_test_folder/World_Census_Agriculture/Country_info_2000/Reports_2/TUV_ENG_REP1_2002.pdf"
        in tooltip
    )


def test_endyear_reported_unemployment_is_visible_with_its_actual_period():
    countries = StaticAssetLoader(GameConfig(ROOT))._load_countries()
    row = _country_row(countries, "SYC")

    tooltip = historical_economic_tooltip(
        row,
        "historical_unemployment_modeled_ilo_pct_2001",
        "3.0%",
        "unemployment rate",
        value_formatter=lambda value: f"{value:.1f}%",
    )

    assert (
        "Alternative historical observation (Reported end-of-year unemployment rate)"
        in tooltip
    )
    assert "4.4 % of labour force" in tooltip
    assert "Observation period: end of calendar year 2001" in tooltip
    assert "Employment Division" in tooltip
