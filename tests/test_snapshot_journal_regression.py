from src.shared.snapshots import StateSnapshotDecoder, StateSnapshotEncoder
from src.shared.state import GameState


def test_delta_journal_payload_does_not_alias_previous_snapshot():
    state = GameState()
    state.journal.domain_events.append({'event_id': 'event', 'payload': {'values': []}})
    encoder, decoder = StateSnapshotEncoder(), StateSnapshotDecoder()
    full = encoder.encode(state)
    previous = decoder.decode(full)
    encoder.acknowledge(full['sequence'])
    current = decoder.decode(encoder.encode(state))
    current.journal.domain_events[0]['payload']['values'].append(123)
    assert previous.journal.domain_events[0]['payload']['values'] == []


def test_replayed_delta_cannot_replace_newer_snapshot():
    import pytest
    from src.shared.snapshots import SnapshotProtocolError

    state = GameState()
    encoder, decoder = StateSnapshotEncoder(), StateSnapshotDecoder()
    full = encoder.encode(state)
    decoder.decode(full)
    encoder.acknowledge(full['sequence'])
    delta = encoder.encode(state)
    previous = decoder.decode(delta)
    with pytest.raises(SnapshotProtocolError, match='not newer'):
        decoder.decode(delta)
    assert decoder.state is previous


def test_full_packet_journal_is_not_shared_between_decodes():
    state = GameState()
    state.journal.command_results.append({'command_id': 'c', 'payload': {'values': []}})
    packet = StateSnapshotEncoder().encode(state)
    first = StateSnapshotDecoder().decode(packet)
    second = StateSnapshotDecoder().decode(packet)
    second.journal.command_results[0]['payload']['values'].append(5)
    assert first.journal.command_results[0]['payload']['values'] == []
    assert packet['journal']['command_results'][0]['payload']['values'] == []
