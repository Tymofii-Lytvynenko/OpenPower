import tempfile
from pathlib import Path

import orjson
import pytest
from hypothesis import given, settings, strategies as st

from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.config import GameConfig
from src.shared.state import GameState
from src.simulation.fingerprint import state_fingerprint
from tests.property.strategies.tables import valid_tables


@pytest.mark.slow
@settings(max_examples=8, deadline=None)
@given(valid_tables(), st.integers(1, 100000), st.lists(st.integers(-100, 100), max_size=5))
def test_save_roundtrip_and_real_v1_migration(frame, seed, values):
    with tempfile.TemporaryDirectory(prefix='openpower-property-') as directory:
        root = Path(directory)
        config = GameConfig(root)
        state = GameState(tables={'sample': frame})
        state.determinism.reset(seed)
        state.globals['nested'] = {'values': values}
        state.system_state['sample'] = {'count': len(values)}
        expected = state_fingerprint(state)
        assert SaveWriter(config).save_game(state, 'slot')
        loaded = DataLoader(config).load_save('slot')
        assert state_fingerprint(loaded) == expected

        meta_path = root / 'user_data' / 'saves' / 'slot' / 'meta.json'
        metadata = orjson.loads(meta_path.read_bytes())
        metadata['version'] = 1
        metadata.pop('determinism')
        metadata.pop('journal')
        metadata.pop('schema_versions')
        meta_path.write_bytes(orjson.dumps(metadata))
        migrated = DataLoader(config).load_save('slot')
        assert migrated.tables['sample'].equals(frame)
        assert migrated.globals == state.globals
        assert migrated.system_state == state.system_state
        assert migrated.determinism.seed == 1
        assert migrated.journal.domain_events == []
