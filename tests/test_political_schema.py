from __future__ import annotations

import polars as pl

from modules.base.schema import build_base_schema_registry, ensure_base_tables
from src.shared.state import GameState


def test_political_schema_adds_lifecycle_tables_without_replacing_legacy_values() -> None:
    state = GameState(
        tables={
            "countries": pl.DataFrame({"id": ["AAA"], "gvt_approval": [73.0]}),
            "country_governments": pl.DataFrame(
                {"country_id": ["AAA"], "government_type": ["Scenario republic"], "next_election": ["2028-01-01"]}
            ),
            "country_laws": pl.DataFrame(
                {"country_id": ["AAA"], "law_id": ["tax"], "value": ["low"]}
            ),
        }
    )

    registry = ensure_base_tables(state)

    government = state.get_table("country_governments").row(0, named=True)
    assert government["government_type"] == "Scenario republic"
    assert government["next_election"] == "2028-01-01"
    assert government["initialized"] is False
    assert state.get_table("country_laws")["value"].to_list() == ["low"]
    assert state.get_table("political_parties").is_empty()
    assert state.get_table("political_elections").is_empty()
    assert registry.get("political_parties").key_columns == ("country_id", "party_id")
    assert registry.get("country_governments").key_columns == ("country_id",)
