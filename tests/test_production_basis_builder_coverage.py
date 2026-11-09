import polars as pl

from modules.base.systems.economy.production_basis_builder import ProductionBasisBuilder
from src.shared.state import GameState


def test_infrastructure_input_without_access_index_keeps_domestic_production() -> None:
    state = GameState(
        tables={"regional_infrastructure": pl.DataFrame({"region_id": [1]})},
    )
    production_basis = pl.DataFrame(
        {"country_id": ["USA"], "domestic_production": [100.0]},
    ).lazy()
    countries = pl.DataFrame({"id": ["USA"]}).lazy()

    result = ProductionBasisBuilder._with_infrastructure(
        production_basis,
        countries,
        {"id"},
        state,
    ).collect()

    assert result.get_column("_effective_production").to_list() == [100.0]
    assert "_industrial_access" not in result.columns
