import polars as pl

from modules.base.systems.economy.input_validation import validate_numeric_columns


def test_empty_tables_skip_numeric_validation():
    frame = pl.DataFrame(schema={"money_reserves": pl.Float64})

    validate_numeric_columns(
        frame,
        "countries",
        ("money_reserves",),
        nonnegative=("money_reserves",),
    )
