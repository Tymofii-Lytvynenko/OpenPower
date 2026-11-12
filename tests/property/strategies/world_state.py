"""Small schema-normalized worlds for tests that need country references."""
import polars as pl
from hypothesis import strategies as st

from modules.base.schema import COUNTRY_RUNTIME_SCHEMA
from src.shared.schema import WorldSchemaRegistry
from src.shared.state import GameState


@st.composite
def world_states(draw):
    country_count = draw(st.integers(1, 10))
    region_count = draw(st.integers(1, 30))
    tags = [f'C{i:02}' for i in range(country_count)]
    owners = draw(st.lists(st.sampled_from(tags), min_size=region_count, max_size=region_count))
    # Regions are data-owned and inferred by the registry, not declared by the base module.
    state = GameState(tables={
        'countries': pl.DataFrame({'id': tags}),
        'regions': pl.DataFrame({'id': list(range(1, region_count + 1)), 'owner': owners}, schema={'id': pl.Int32, 'owner': pl.String}),
    })
    registry = WorldSchemaRegistry((COUNTRY_RUNTIME_SCHEMA,))
    registry.capture_state(state)
    registry.ensure_state(state)
    return state
