from hypothesis import given

from tests.property.strategies.tables import TABLE_SCHEMA, valid_tables


@given(valid_tables())
def test_generated_tables_match_declared_schema(frame):
    assert frame.schema == {name: spec.dtype for name, spec in TABLE_SCHEMA.columns.items()}
    assert frame['id'].n_unique() == frame.height

from tests.property.strategies.world_state import world_states


@given(world_states())
def test_generated_world_has_schema_and_valid_ownership(state):
    assert not state.schema_registry.validate_state(state)
    countries = state.tables['countries']
    regions = state.tables['regions']
    assert countries['id'].n_unique() == countries.height
    assert regions['id'].n_unique() == regions.height
    assert set(regions['owner']) <= set(countries['id'])
