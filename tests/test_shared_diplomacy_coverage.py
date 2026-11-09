from types import SimpleNamespace

import polars as pl

from src.shared.diplomacy import countries_at_war


def test_countries_at_war_returns_false_without_war_tables_or_required_sides():
    assert not countries_at_war(SimpleNamespace(tables={}), "USA", "CAN")

    state = SimpleNamespace(
        tables={"countries_wars": pl.DataFrame({"side_a": [["USA"]]})}
    )
    assert not countries_at_war(state, "USA", "CAN")
