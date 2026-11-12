import polars as pl
from hypothesis import strategies as st

from src.shared.schema import ColumnSpec, TableSchema

TABLE_SCHEMA = TableSchema(
    "sample", {"id": ColumnSpec(pl.Int64), "value": ColumnSpec(pl.Int64, 7)},
    key_columns=("id",),
)

@st.composite
def valid_tables(draw):
    ids = draw(st.lists(st.integers(0, 1000), unique=True, min_size=1, max_size=10))
    values = draw(st.lists(st.integers(-1000, 1000), min_size=len(ids), max_size=len(ids)))
    return pl.DataFrame({"id": ids, "value": values}, schema={name: spec.dtype for name, spec in TABLE_SCHEMA.columns.items()})
