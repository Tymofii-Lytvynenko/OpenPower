import polars as pl
import pytest
from hypothesis import given, strategies as st

from src.shared.schema import ColumnSpec, TableSchema, WorldSchemaRegistry
from src.shared.state import GameState
from tests.property.strategies.tables import TABLE_SCHEMA, valid_tables


@given(valid_tables(), st.booleans())
def test_normalization_preserves_values_and_is_idempotent(frame, preserve):
    schema = TableSchema('sample', TABLE_SCHEMA.columns, ('id',), preserve_extra_columns=preserve)
    registry = WorldSchemaRegistry([schema])
    extra = frame.with_columns(pl.lit('extra').alias('extra'))
    normalized = registry.normalize('sample', extra)
    assert normalized.select(frame.columns).equals(frame)
    assert ('extra' in normalized.columns) == preserve
    assert registry.normalize('sample', normalized).equals(normalized)
    assert normalized.schema['id'] == pl.Int64


@given(valid_tables())
def test_missing_column_defaults_and_invalid_keys(frame):
    registry = WorldSchemaRegistry([TABLE_SCHEMA])
    normalized = registry.normalize('sample', frame.select('id'))
    assert normalized['value'].to_list() == [7] * frame.height
    duplicate = pl.concat([frame, frame.head(1)])
    null_key = frame.with_columns(pl.lit(None, dtype=pl.Int64).alias('id'))
    assert 'duplicate_key' in {i.code for i in registry.validate_state(GameState(tables={'sample': duplicate}))}
    assert 'null_key' in {i.code for i in registry.validate_state(GameState(tables={'sample': null_key}))}


@given(st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=8))
def test_incompatible_cast_and_conflicting_schema_rejected(text):
    registry = WorldSchemaRegistry([TABLE_SCHEMA])
    with pytest.raises(pl.exceptions.InvalidOperationError):
        registry.normalize('sample', pl.DataFrame({'id': [text], 'value': [1]}))
    with pytest.raises(RuntimeError, match='conflict'):
        registry.register(TableSchema('sample', {'id': ColumnSpec(pl.String)}))
