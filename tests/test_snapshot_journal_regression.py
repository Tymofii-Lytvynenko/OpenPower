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
