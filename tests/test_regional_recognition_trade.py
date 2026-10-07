from __future__ import annotations

import polars as pl
import pytest

from modules.base.systems.economy.trade_system import TradeSystem
from modules.base.systems.economy.treaty_trade_policy import TreatyTradePolicy
from modules.base.systems.world.recognition_policy import regional_trade_access_allowed
from src.shared.state import GameState


def _recognition_state(case_status: str | None = "pending", recognized: tuple[str, ...] = ()) -> GameState:
    state = GameState()
    state.update_table(
        "regions",
        pl.DataFrame(
            {
                "id": [17],
                "owner": ["AAA"],
                "controller": ["AAA"],
            }
        ),
    )
    case_rows = []
    if case_status is not None:
        case_rows.append(
            {
                "id": "case-17",
                "region_id": 17,
                "claimant_id": "AAA",
                "status": case_status,
            }
        )
    state.update_table(
        "recognition_cases",
        pl.DataFrame(
            case_rows,
            schema={
                "id": pl.Utf8,
                "region_id": pl.Int32,
                "claimant_id": pl.Utf8,
                "status": pl.Utf8,
            },
        ),
    )
    state.update_table(
        "regional_recognition_status",
        pl.DataFrame(
            [
                {
                    "id": f"status-{country_id}",
                    "case_id": "case-17",
                    "region_id": 17,
                    "claimant_id": "AAA",
                    "country_id": country_id,
                    "status": "recognized",
                    "withdrawn_at_minute": 0,
                }
                for country_id in recognized
            ],
            schema={
                "id": pl.Utf8,
                "case_id": pl.Utf8,
                "region_id": pl.Int32,
                "claimant_id": pl.Utf8,
                "country_id": pl.Utf8,
                "status": pl.Utf8,
                "withdrawn_at_minute": pl.Int64,
            },
        ),
    )
    return state


def test_regional_trade_access_only_gates_regions_with_an_active_recognition_case():
    state = _recognition_state("pending")
    assert regional_trade_access_allowed(state, 17, "AAA", "AAA")
    assert not regional_trade_access_allowed(state, 17, "AAA", "BBB")

    passed = _recognition_state("passed", ("BBB",))
    assert regional_trade_access_allowed(passed, 17, "AAA", "BBB")
    assert not regional_trade_access_allowed(passed, 17, "AAA", "CCC")

    ordinary_region = _recognition_state(None)
    assert regional_trade_access_allowed(ordinary_region, 17, "AAA", "CCC")

    seeded_regions = ordinary_region.get_table("regions").drop("controller")
    ordinary_region.update_table("regions", seeded_regions)
    assert regional_trade_access_allowed(ordinary_region, 17, "AAA", "CCC")


def test_explicit_regional_supply_cannot_flow_to_nonrecognizing_importer():
    market = pl.DataFrame(
        {
            "country_id": ["AAA", "BBB", "CCC"],
            "game_resource_id": ["cereals"] * 3,
            "export_desired": [100.0, 0.0, 0.0],
            "affordable_import": [0.0, 70.0, 70.0],
        }
    )
    regional_production = pl.DataFrame(
        {
            "country_id": ["AAA"],
            "region_id": [17],
            "game_resource_id": ["cereals"],
            "domestic_production": [100.0],
        }
    )
    state = _recognition_state("passed", ("BBB",))

    flows = TreatyTradePolicy().allocate_with_regional_sources(
        market,
        pl.DataFrame(),
        regional_production,
        lambda region_id, exporter_id, importer_id: regional_trade_access_allowed(
            state, region_id, exporter_id, importer_id
        ),
    )

    assert flows.to_dicts() == [
        {
            "exporter_id": "AAA",
            "importer_id": "BBB",
            "game_resource_id": "cereals",
            "trade_value_usd": 70.0,
            "source_region_id": 17,
        }
    ]


def test_national_remainder_is_not_falsely_attributed_to_a_region():
    market = pl.DataFrame(
        {
            "country_id": ["AAA", "BBB"],
            "game_resource_id": ["cereals", "cereals"],
            "export_desired": [100.0, 0.0],
            "affordable_import": [0.0, 100.0],
        }
    )
    regional_production = pl.DataFrame(
        {
            "country_id": ["AAA"],
            "region_id": [17],
            "game_resource_id": ["cereals"],
            "domestic_production": [40.0],
        }
    )

    flows = TreatyTradePolicy().allocate_with_regional_sources(
        market,
        pl.DataFrame(),
        regional_production,
        lambda _region_id, _exporter_id, _importer_id: False,
    )

    assert sum(row["trade_value_usd"] for row in flows.to_dicts()) == 60.0
    assert flows.filter(pl.col("source_region_id").is_null())["trade_value_usd"].sum() == 60.0


def test_regional_output_must_be_backed_by_national_production_without_being_inferred():
    market = pl.DataFrame(
        {
            "country_id": ["AAA"],
            "game_resource_id": ["cereals"],
            "export_desired": [10.0],
            "affordable_import": [0.0],
            "domestic_production": [10.0],
        }
    )
    regional_production = pl.DataFrame(
        {
            "country_id": ["AAA"],
            "region_id": [17],
            "game_resource_id": ["cereals"],
            "domestic_production": [11.0],
        }
    )

    with pytest.raises(ValueError, match="exceeds national production"):
        TreatyTradePolicy().allocate_with_regional_sources(
            market,
            pl.DataFrame(),
            regional_production,
            lambda _region_id, _exporter_id, _importer_id: True,
        )


def test_trade_system_publishes_region_provenance_and_blocks_nonrecognizing_importer():
    state = _recognition_state("passed", ("BBB",))
    state.update_table(
        "countries",
        pl.DataFrame({"id": ["AAA", "BBB", "CCC"]}),
    )
    state.update_table(
        "domestic_production",
        pl.DataFrame(
            {
                "country_id": ["AAA", "BBB", "CCC"],
                "game_resource_id": ["cereals"] * 3,
                "domestic_production": [100.0, 0.0, 0.0],
                "is_legal": [True, True, True],
                "is_gov_controlled": [False, False, False],
                "tax_rate": [0.0, 0.0, 0.0],
            }
        ),
    )
    state.update_table(
        "resource_ledger",
        pl.DataFrame(
            {
                "country_id": ["AAA", "BBB", "CCC"],
                "game_resource_id": ["cereals"] * 3,
                "consumption_usd": [0.0, 70.0, 70.0],
            }
        ),
    )
    state.update_table(
        "regional_production",
        pl.DataFrame(
            {
                "id": ["AAA:17:cereals"],
                "country_id": ["AAA"],
                "region_id": [17],
                "game_resource_id": ["cereals"],
                "domestic_production": [100.0],
            }
        ),
    )

    TradeSystem()._simulate_market_cycle(state, 1.0 / 365.25)

    flows = state.get_table("trade_network")
    assert flows.select("exporter_id", "importer_id", "source_region_id").to_dicts() == [
        {"exporter_id": "AAA", "importer_id": "BBB", "source_region_id": 17}
    ]
    assert flows["trade_value_usd"].to_list() == [70.0]


def test_empty_regional_source_table_preserves_existing_world_market_flow_contract():
    state = GameState(
        tables={
            "countries": pl.DataFrame({"id": ["AAA", "BBB"]}),
            "domestic_production": pl.DataFrame(
                {
                    "country_id": ["AAA", "BBB"],
                    "game_resource_id": ["cereals", "cereals"],
                    "domestic_production": [100.0, 0.0],
                }
            ),
            "resource_ledger": pl.DataFrame(
                {
                    "country_id": ["AAA", "BBB"],
                    "game_resource_id": ["cereals", "cereals"],
                    "consumption_usd": [0.0, 60.0],
                }
            ),
        }
    )

    TradeSystem()._simulate_market_cycle(state, 1.0 / 365.25)

    flows = state.get_table("trade_network")
    assert flows.select("exporter_id", "importer_id").to_dicts() == [
        {"exporter_id": "AAA", "importer_id": "WORLD"},
        {"exporter_id": "WORLD", "importer_id": "BBB"},
    ]
    assert flows["trade_value_usd"].to_list() == [60.0, 60.0]
    assert "source_region_id" not in flows.columns
