from copy import deepcopy

import polars as pl
import pytest
from hypothesis import given, strategies as st

from src.shared.snapshots import SnapshotProtocolError, StateSnapshotDecoder, StateSnapshotEncoder
from src.shared.state import GameState
from tests.property.strategies.tables import valid_tables


@given(valid_tables(), st.lists(st.integers(-100, 100), max_size=8), st.lists(st.integers(-100, 100), max_size=8))
def test_full_acknowledged_deltas_and_history_append(frame, updates, history):
    state = GameState(tables={'sample': frame, 'history_snapshots': pl.DataFrame({'value': history}, schema={'value': pl.Int64})})
    state.globals['nested'] = {'values': [1]}
    encoder, decoder = StateSnapshotEncoder(), StateSnapshotDecoder()
    packet = encoder.encode(state)
    published = decoder.decode(packet)
    encoder.acknowledge(packet['sequence'])
    for value in updates:
        state.update_table('sample', pl.DataFrame({'value': [value]}))
        state.update_table('history_snapshots', pl.concat([state.tables['history_snapshots'], pl.DataFrame({'value': [value]}, schema={'value': pl.Int64})]))
        state.globals['nested']['values'].append(value)
        packet = encoder.encode(state)
        decoded = decoder.decode(packet)
        assert all(decoded.tables[name].equals(table) for name, table in state.tables.items())
        assert decoded.globals == state.globals
        encoder.acknowledge(packet['sequence'])
    assert published.globals['nested']['values'] == [1]
    state.remove_table('sample')
    decoded = decoder.decode(encoder.encode(state))
    assert set(decoded.tables) == set(state.tables)


@given(valid_tables())
def test_invalid_snapshot_version_and_missing_base_rejected(frame):
    encoder = StateSnapshotEncoder()
    state = GameState(tables={'sample': frame})
    packet = encoder.encode(state)
    invalid = deepcopy(packet)
    invalid['protocol_version'] += 1
    with pytest.raises(SnapshotProtocolError):
        StateSnapshotDecoder().decode(invalid)
    encoder.acknowledge(packet['sequence'])
    delta = encoder.encode(state)
    with pytest.raises(SnapshotProtocolError):
        StateSnapshotDecoder().decode(delta)
    decoder = StateSnapshotDecoder()
    decoder.decode(packet)
    delta['base_sequence'] = packet['sequence'] + 10
    with pytest.raises(SnapshotProtocolError):
        decoder.decode(delta)

@given(st.lists(st.integers(-100, 100), max_size=5))
def test_published_snapshot_journal_records_are_independent(values):
    state = GameState()
    state.journal.domain_events.append({'event_id': 'event', 'payload': {'values': values.copy()}})
    encoder, decoder = StateSnapshotEncoder(), StateSnapshotDecoder()
    packet = encoder.encode(state)
    first = decoder.decode(packet)
    encoder.acknowledge(packet['sequence'])
    second = decoder.decode(encoder.encode(state))
    second.journal.domain_events[0]['payload']['values'].append(123)
    assert first.journal.domain_events[0]['payload']['values'] == values

@given(valid_tables())
def test_replayed_delta_is_rejected_without_mutating_decoder(frame):
    state = GameState(tables={'sample': frame})
    encoder, decoder = StateSnapshotEncoder(), StateSnapshotDecoder()
    full = encoder.encode(state)
    decoder.decode(full)
    encoder.acknowledge(full['sequence'])
    delta = encoder.encode(state)
    current = decoder.decode(delta)
    with pytest.raises(SnapshotProtocolError):
        decoder.decode(delta)
    assert decoder.state is current
    assert decoder.sequence == delta['sequence']

@given(st.lists(st.integers(-100, 100), max_size=5))
def test_full_snapshot_decoding_is_independent_of_packet_and_other_decodes(values):
    state = GameState()
    state.journal.command_results.append({'command_id': 'c', 'payload': {'values': values.copy()}})
    packet = StateSnapshotEncoder().encode(state)
    first = StateSnapshotDecoder().decode(packet)
    second = StateSnapshotDecoder().decode(packet)
    second.journal.command_results[0]['payload']['values'].append(5)
    assert first.journal.command_results[0]['payload']['values'] == values
    assert packet['journal']['command_results'][0]['payload']['values'] == values
