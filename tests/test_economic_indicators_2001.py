import csv
import json
import math
from types import SimpleNamespace

import polars as pl
import pytest

import src.client.ui.panels.economic_health_panel as economic_panel_module
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.economic_health_panel import EconomicHealthPanel
from src.client.ui.panels.historical_economic_baseline import (
    historical_economic_tooltip,
)
from src.server.io.static_loader import StaticAssetLoader
from src.shared.config import GameConfig
from utils.import_economic_indicators_2001 import (
    ALL_INDICATORS,
    COUNTRY_EXTENSION_PATH,
    IMF_WEO_ALTERNATIVES,
    IMF_WEO_FALLBACKS,
    INDICATORS,
    LEDGER_PATH,
    REPORT_PATH,
    ROOT,
    parse_imf_weo_payload,
    parse_wdi_payload,
    read_country_ids,
)


def _wdi_row(country_id, year, value, country_name="Test country"):
    return {
        "countryiso3code": country_id,
        "country": {"value": country_name},
        "date": str(year),
        "value": value,
    }


def test_wdi_parser_selects_only_exact_finite_country_observations():
    payload = json.dumps(
        [
            {"page": 1, "pages": 1},
            [
                _wdi_row("AAA", 2000, 12),
                _wdi_row("AAA", 2001, 0),
                _wdi_row("BBB", 2001, 3.5),
                _wdi_row("CCC", 2001, None),
                _wdi_row("DDD", 2001, "NaN"),
                _wdi_row("ZZZ", 2001, 9, "World"),
            ],
        ]
    ).encode()

    result = parse_wdi_payload(payload, "NY.TEST", {"AAA", "BBB", "CCC", "DDD"})

    assert result == {
        "AAA": {"value": 0.0, "observation_year": 2001, "country_name": "Test country"},
        "BBB": {"value": 3.5, "observation_year": 2001, "country_name": "Test country"},
    }


def test_wdi_parser_rejects_duplicate_exact_country_observations():
    payload = json.dumps(
        [
            {"page": 1, "pages": 1},
            [_wdi_row("AAA", 2001, 1), _wdi_row("AAA", 2001, 2)],
        ]
    ).encode()

    with pytest.raises(ValueError, match="Duplicate NY.TEST observation for AAA"):
        parse_wdi_payload(payload, "NY.TEST", {"AAA"})


def test_imf_weo_parser_selects_exact_year_and_maps_kosovo_code():
    payload = json.dumps(
        {
            "indicators": {"NGDPD": {"label": "GDP, current prices"}},
            "values": {
                "NGDPD": {
                    "UVK": {"2000": 2.1, "2001": 2.509, "2002": 2.7},
                    "TWN": {"2001": 299.276},
                    "WEO_WORLD": {"2001": 300.0},
                }
            },
        }
    ).encode()

    result = parse_imf_weo_payload(
        payload,
        "NGDPD",
        {"KOS", "TWN", "USA"},
        scale=1_000_000_000,
    )

    assert result == {
        "KOS": {
            "value": 2_509_000_000.0,
            "observation_year": 2001,
            "source_country_code": "UVK",
        },
        "TWN": {
            "value": 299_276_000_000.0,
            "observation_year": 2001,
            "source_country_code": "TWN",
        },
    }


def test_generated_extension_and_ledger_keep_exact_year_coverage_and_provenance():
    country_ids = read_country_ids()
    with COUNTRY_EXTENSION_PATH.open(encoding="utf-8", newline="") as stream:
        extension_rows = list(csv.DictReader(stream, delimiter="\t"))
    with LEDGER_PATH.open(encoding="utf-8", newline="") as stream:
        ledger_rows = list(csv.DictReader(stream, delimiter="\t"))

    assert len(country_ids) == 209
    assert [row["id"] for row in extension_rows] == country_ids
    assert len({row["id"] for row in extension_rows}) == len(country_ids)
    assert not {"gdp", "inflation_rate", "unemployment_rate"}.intersection(
        extension_rows[0]
    )
    assert len(ledger_rows) == sum(
        int(row[f"{field}_available"] == "true")
        for row in extension_rows
        for field in ALL_INDICATORS
    )

    expected_coverage = {
        "historical_gdp_current_usd_2001": 198,
        "historical_gdp_per_capita_current_usd_2001": 198,
        "historical_inflation_cpi_pct_2001": 188,
        "historical_unemployment_modeled_ilo_pct_2001": 181,
        "historical_unemployment_imf_weo_pct_2001": 3,
    }
    expected_world_bank_coverage = {
        "historical_gdp_current_usd_2001": 196,
        "historical_gdp_per_capita_current_usd_2001": 196,
        "historical_inflation_cpi_pct_2001": 165,
        "historical_unemployment_modeled_ilo_pct_2001": 181,
    }
    expected_imf_supplements = {
        "historical_gdp_current_usd_2001": {"KOS", "TWN"},
        "historical_gdp_per_capita_current_usd_2001": {"KOS", "TWN"},
        "historical_inflation_cpi_pct_2001": {
            "ARE",
            "ARG",
            "BIH",
            "ERI",
            "GIN",
            "KIR",
            "KOS",
            "LBN",
            "LBR",
            "LIE",
            "MNE",
            "MOZ",
            "NAM",
            "PLW",
            "PRI",
            "SLE",
            "TKM",
            "TLS",
            "TUV",
            "TWN",
            "UZB",
            "VEN",
            "ZWE",
        },
    }
    expected_remaining_gaps = {
        "historical_gdp_current_usd_2001": {
            "AIA",
            "ATA",
            "ESH",
            "MSR",
            "PRK",
            "SHN",
            "SSD",
            "SXM",
            "UMI",
            "VAT",
            "WLF",
        },
        "historical_gdp_per_capita_current_usd_2001": {
            "AIA",
            "ATA",
            "ESH",
            "MSR",
            "PRK",
            "SHN",
            "SSD",
            "SXM",
            "UMI",
            "VAT",
            "WLF",
        },
        "historical_inflation_cpi_pct_2001": {
            "AFG",
            "AIA",
            "AND",
            "ATA",
            "BMU",
            "CUB",
            "ESH",
            "GRL",
            "MCO",
            "MHL",
            "MSR",
            "NRU",
            "PRK",
            "SHN",
            "SMR",
            "SOM",
            "SSD",
            "SXM",
            "UMI",
            "VAT",
            "WLF",
        },
        "historical_unemployment_modeled_ilo_pct_2001": {
            "AIA",
            "AND",
            "ATA",
            "ATG",
            "BMU",
            "DMA",
            "ESH",
            "FSM",
            "GRD",
            "GRL",
            "KIR",
            "KNA",
            "KOS",
            "LIE",
            "MCO",
            "MHL",
            "MSR",
            "NRU",
            "PLW",
            "SHN",
            "SMR",
            "SXM",
            "SYC",
            "TUV",
            "TWN",
            "UMI",
            "VAT",
            "WLF",
        },
    }
    ledger_index = {(row["country_id"], row["field"]): row for row in ledger_rows}
    for field, expected_count in expected_coverage.items():
        assert (
            sum(row[f"{field}_available"] == "true" for row in extension_rows)
            == expected_count
        )
        for row in extension_rows:
            available = row[f"{field}_available"] == "true"
            provenance = json.loads(row["historical_economic_provenance_json"])
            key = (row["id"], field)
            if not available:
                assert row[field] == ""
                assert field not in provenance
                assert key not in ledger_index
                continue

            value = float(row[field])
            assert math.isfinite(value)
            source = provenance[field]
            ledger = ledger_index[key]
            assert source["scenario_year"] == source["observation_year"] == 2001
            if source["source"].startswith("World Bank"):
                assert source["indicator"] == INDICATORS[field]["code"]
                assert source["source_url"].startswith(
                    "https://data.worldbank.org/indicator/"
                )
            else:
                definition = (
                    IMF_WEO_ALTERNATIVES[field]
                    if field in IMF_WEO_ALTERNATIVES
                    else IMF_WEO_FALLBACKS[field]
                )
                assert source["source"] == "World Economic Outlook, October 2026"
                assert source["indicator"] == definition["code"]
                assert source["source_url"].startswith(
                    "https://www.imf.org/external/datamapper/api/v2/"
                )
            assert source["source_note"]
            assert ledger["scenario_year"] == ledger["observation_year"] == "2001"
            assert float(ledger["value"]) == value
            assert ledger["source_url"] == source["source_url"]
            assert ledger["source_note"] == source["source_note"]
            assert ledger["source_release"] == source["source_release"]

    report = REPORT_PATH.read_text(encoding="utf-8")
    for field, count in expected_coverage.items():
        assert f"`{field}`" in report
        assert f"{count}/209" in report
    for field, count in expected_world_bank_coverage.items():
        assert (
            sum(
                field in json.loads(row["historical_economic_provenance_json"])
                and json.loads(row["historical_economic_provenance_json"])[field][
                    "source"
                ].startswith("World Bank")
                for row in extension_rows
            )
            == count
        )
    for field, expected_ids in expected_imf_supplements.items():
        actual_ids = {
            row["id"]
            for row in extension_rows
            if field in json.loads(row["historical_economic_provenance_json"])
            and json.loads(row["historical_economic_provenance_json"])[field][
                "source"
            ].startswith("World Economic Outlook")
        }
        assert actual_ids == expected_ids
    for field, expected_ids in expected_remaining_gaps.items():
        assert {
            row["id"] for row in extension_rows if row[f"{field}_available"] != "true"
        } == expected_ids

    assert {
        row["id"]
        for row in extension_rows
        if row["historical_unemployment_imf_weo_pct_2001_available"] == "true"
    } == {"SMR", "SYC", "TWN"}
    assert {
        row["id"]
        for row in extension_rows
        if row["historical_gdp_current_usd_2001_available"] == "true"
        and json.loads(row["historical_economic_provenance_json"])[
            "historical_gdp_current_usd_2001"
        ]["source"].startswith("World Economic Outlook")
    } == {"KOS", "TWN"}


def test_static_country_loader_merges_historical_economy_without_replacing_live_gdp():
    countries = StaticAssetLoader(GameConfig(ROOT))._load_countries()
    usa = countries.filter(pl.col("id") == "USA").row(0, named=True)
    kosovo = countries.filter(pl.col("id") == "KOS").row(0, named=True)

    assert countries.height == 209
    assert not {"gdp", "inflation_rate", "unemployment_rate"}.intersection(
        countries.columns
    )
    assert usa["historical_gdp_current_usd_2001"] == pytest.approx(10_581_929_000_000)
    assert usa["historical_gdp_current_usd_2001_available"] is True
    assert usa["historical_economic_provenance_json"]
    assert kosovo["historical_gdp_current_usd_2001"] == pytest.approx(2_509_000_000)
    assert kosovo["historical_gdp_current_usd_2001_available"] is True
    assert (
        '"source_country_code_mapping"' in kosovo["historical_economic_provenance_json"]
    )


def test_presenter_tooltip_separates_live_value_from_dated_wdi_baseline():
    field = "historical_gdp_current_usd_2001"
    source_url = "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD"
    row = {
        field: 1234.0,
        f"{field}_available": True,
        "historical_economic_provenance_json": json.dumps(
            {
                field: {
                    "scenario_year": 2001,
                    "observation_year": 2001,
                    "source": "World Bank, World Development Indicators",
                    "indicator": "NY.GDP.MKTP.CD",
                    "source_url": source_url,
                    "source_note": "Nominal GDP, current US dollars.",
                    "unit": "current US$",
                }
            }
        ),
    }

    tooltip = historical_economic_tooltip(
        row,
        field,
        "$ 5,000",
        "GDP",
        value_formatter=lambda value: f"$ {value:,.0f}",
    )

    assert "Current simulated GDP: $ 5,000" in tooltip
    assert "This displayed value remains OpenPower simulation state." in tooltip
    assert (
        "2001 historical baseline (GDP (current US$)): $ 1,234 (current US$)."
        in tooltip
    )
    assert "Source observation year: 2001; scenario year: 2001." in tooltip
    assert "Nominal GDP, current US dollars." in tooltip
    assert source_url in tooltip


def test_presenter_tooltip_marks_missing_exact_year_as_unavailable_not_zero():
    field = "historical_inflation_cpi_pct_2001"
    tooltip = historical_economic_tooltip(
        {
            field: 0,
            f"{field}_available": False,
            "historical_economic_provenance_json": "{}",
        },
        field,
        "2.0%",
        "inflation rate",
    )

    assert "Current simulated inflation rate: 2.0%" in tooltip
    assert "unavailable for FP.CPI.TOTL.ZG" in tooltip
    assert "no exact-year observation" in tooltip
    assert "no neighboring-year value was substituted" in tooltip
    assert "baseline: 0" not in tooltip


def test_presenter_keeps_imf_unemployment_alternative_separate_from_modeled_ilo():
    ilo_field = "historical_unemployment_modeled_ilo_pct_2001"
    imf_field = "historical_unemployment_imf_weo_pct_2001"
    imf_provenance = {
        "scenario_year": 2001,
        "observation_year": 2001,
        "source": "World Economic Outlook, October 2026",
        "indicator": "LUR",
        "source_url": "https://www.imf.org/external/datamapper/api/v2/LUR?periods=2001",
        "source_note": "Separate IMF unemployment rate, not modeled ILOEST.",
        "unit": "% of labor force",
    }
    tooltip = historical_economic_tooltip(
        {
            ilo_field: 0,
            f"{ilo_field}_available": False,
            imf_field: 4.6,
            f"{imf_field}_available": True,
            "historical_economic_provenance_json": json.dumps(
                {imf_field: imf_provenance}
            ),
        },
        ilo_field,
        "3.5%",
        "unemployment rate",
        value_formatter=lambda value: f"{value:.1f}%",
    )

    assert "unavailable for SL.UEM.TOTL.ZS" in tooltip
    assert "Alternative historical observation (IMF WEO unemployment rate" in tooltip
    assert "4.6 % of labor force" in tooltip
    assert "Separate IMF unemployment rate, not modeled ILOEST." in tooltip
    assert imf_provenance["source_url"] in tooltip


def test_economic_panel_keeps_live_metrics_and_attaches_historical_tooltips(
    monkeypatch,
):
    widgets = []

    class FakeGMLWidgets:
        def __init__(self, _layout):
            self.calls = []
            widgets.append(self)

        def frame(self, *_args, **_kwargs):
            pass

        def text(self, *args, **kwargs):
            self.calls.append((args, kwargs))

        def rule(self, *_args, **_kwargs):
            pass

        def input_float(self, _path, _label, value, _test_id, **_kwargs):
            return False, value

        def button(self, *_args, **_kwargs):
            return False

        def button_at(self, *_args, **_kwargs):
            return False

    class FakeImGui:
        @staticmethod
        def begin_popup(*_args, **_kwargs):
            return False

    monkeypatch.setattr(economic_panel_module, "GMLWidgets", FakeGMLWidgets)
    monkeypatch.setattr(economic_panel_module, "imgui", FakeImGui())
    panel = EconomicHealthPanel()
    panel._render_source_rate_control = lambda *_args, **_kwargs: None
    panel._draw_population_meter = lambda *_args, **_kwargs: None
    panel._draw_inflation_meter = lambda *_args, **_kwargs: None

    provenance = {
        field: {
            "scenario_year": 2001,
            "observation_year": 2001,
            "source": "World Bank, World Development Indicators",
            "indicator": definition["code"],
            "source_url": f"https://data.worldbank.org/indicator/{definition['code']}",
            "source_note": definition["note"],
            "unit": definition["unit"],
        }
        for field, definition in INDICATORS.items()
    }
    row = pl.DataFrame(
        [
            {
                "gdp": 5000.0,
                "historical_gdp_current_usd_2001": 1000.0,
                "historical_gdp_current_usd_2001_available": True,
                "historical_gdp_per_capita_current_usd_2001": 25.0,
                "historical_gdp_per_capita_current_usd_2001_available": True,
                "historical_inflation_cpi_pct_2001": 2.0,
                "historical_inflation_cpi_pct_2001_available": True,
                "historical_unemployment_modeled_ilo_pct_2001": 6.0,
                "historical_unemployment_modeled_ilo_pct_2001_available": True,
                "historical_economic_provenance_json": json.dumps(provenance),
            }
        ]
    )
    state = SimpleNamespace(
        tables={
            "regions": pl.DataFrame(
                [
                    {
                        "owner": "UKR",
                        "pop_14": 10,
                        "pop_15_64": 80,
                        "pop_65": 10,
                    }
                ]
            )
        },
        globals={},
    )
    context = PanelRenderContext("UKR", True)
    panel._render_source_content(
        state,
        context,
        row,
        SimpleNamespace(unemployment_rate=0.08, poverty_rate=0.2, inflation_rate=0.04),
    )

    rendered = {
        kwargs["test_id"]: (args[1], kwargs.get("tooltip", ""))
        for args, kwargs in widgets[0].calls
        if kwargs.get("test_id")
        in {
            "economic_health.gdp",
            "economic_health.gdp_per_capita",
            "economic_health.unemployment",
            "economic_health.inflation",
        }
    }
    assert rendered["economic_health.gdp"][0] == "$ 5 000"
    assert rendered["economic_health.gdp_per_capita"][0] == "$ 50"
    assert rendered["economic_health.unemployment"][0] == "8.0%"
    assert rendered["economic_health.inflation"][0] == "4.0%"
    assert all("Current simulated" in tooltip for _value, tooltip in rendered.values())
    assert all(
        "Source observation year: 2001" in tooltip
        for _value, tooltip in rendered.values()
    )
