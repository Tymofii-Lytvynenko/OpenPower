from hypothesis import given

from tests.property.strategies.tables import TABLE_SCHEMA, valid_tables


@given(valid_tables())
def test_generated_tables_match_declared_schema(frame):
    assert frame.schema == {name: spec.dtype for name, spec in TABLE_SCHEMA.columns.items()}
    assert frame['id'].n_unique() == frame.height
