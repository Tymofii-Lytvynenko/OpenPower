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

@st.composite
def missing_columns(draw):
    frame = draw(valid_tables())
    return frame.drop(draw(st.sampled_from(tuple(TABLE_SCHEMA.columns))))


@st.composite
def wrong_type_tables(draw):
    text = draw(st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=8))
    return pl.DataFrame({'id': [text], 'value': [0]})


@st.composite
def duplicate_key_tables(draw):
    frame = draw(valid_tables())
    return pl.concat([frame, frame.head(1)])


@st.composite
def null_key_tables(draw):
    frame = draw(valid_tables())
    return frame.with_columns(pl.lit(None, dtype=TABLE_SCHEMA.columns['id'].dtype).alias('id'))


@st.composite
def tables_with_extras(draw):
    frame = draw(valid_tables())
    extra = draw(st.integers(-100, 100))
    return frame.with_columns(pl.lit(extra).alias('extra'))
