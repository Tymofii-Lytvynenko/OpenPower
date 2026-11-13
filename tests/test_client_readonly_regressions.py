from dataclasses import dataclass, field

import polars as pl

from modules.base.schema import ensure_base_tables
from src.client.client_state import ClientGameStateView, ClientPresentationState
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.politics.political_overview_presenter import (
    PoliticalOverviewPresenter,
)
from src.client.ui.panels.service.event_feed_presenter import EventFeedPresenter
from src.shared.state import GameState
from tests.test_support.client_presentation import presentation_values


def view(state):
    return ClientGameStateView(state, presentation_values(), ClientPresentationState())


def test_political_overview_reads_snapshot_tables():
    state = GameState(tables={
        'countries': pl.DataFrame({'id': ['AAA'], 'gvt_approval': [0.71]}),
        'country_governments': pl.DataFrame({'country_id': ['AAA'], 'government_type': ['Democracy']}),
    })
    actual = PoliticalOverviewPresenter().build(view(state), 'AAA')
    assert actual.government_form == 'Democracy'
    assert actual.approval_pct == 71.0


def test_event_feed_reads_frozen_world_events():
    state = GameState(tables={'regions': pl.DataFrame({'id': [7], 'name': ['Odesa'], 'owner': ['UKR']})})
    state.globals['active_events'] = [{'id': 'flood', 'event_type': 'flood', 'label': 'Flood',
                                       'region_id': 7, 'severity': 0.8, 'start_minute': 120}]
    items = EventFeedPresenter().items(view(state))
    assert len(items) == 1
    assert items[0].headline == 'Flood'
    assert 'Odesa' in items[0].summary


def test_strategic_payload_profiles_read_frozen_overrides():
    state = GameState()
    state.globals['strategic_payload_profiles'] = {'1': {'yield_kt': 55, 'blast_radius_km': 12}}
    assert MilitaryPresenter().strategic_payload_profiles(view(state))[1] == (55.0, 12.0)


def test_foreign_order_permissions_accept_snapshot_pairs():
    state = GameState(tables={'countries': pl.DataFrame({'id': ['USA', 'CAN']})})
    ensure_base_tables(state)
    state.update_table('unit_designs', pl.DataFrame([{'id': 'd', 'country_id': 'CAN', 'display_name': 'Infantry'}], schema=state.get_table('unit_designs').schema))
    state.update_table('unit_market_listings', pl.DataFrame([{'id': 'l', 'seller_country_id': 'CAN', 'design_id': 'd', 'quantity': 2, 'status': 'listed'}], schema=state.get_table('unit_market_listings').schema))
    state.globals['foreign_order_permissions'] = [['USA', 'CAN']]
    presenter = MilitaryPresenter()
    snapshot = view(state)
    assert [row['id'] for row in presenter.foreign_designs_for_country(snapshot, 'USA')] == ['d']
    assert [row['id'] for row in presenter.market_listings_for_country(snapshot, 'USA')] == ['l']


@dataclass
class MutableRecord:
    payload: dict = field(default_factory=lambda: {'items': [1]})


def test_event_and_action_objects_are_detached_on_every_read():
    state = GameState(events=[MutableRecord()], current_actions=[MutableRecord()])
    snapshot = view(state)
    snapshot.events[0].payload['items'].append(2)
    snapshot.current_actions[0].payload['items'].append(3)
    assert state.events[0].payload['items'] == [1]
    assert state.current_actions[0].payload['items'] == [1]
    assert snapshot.events[0].payload['items'] == [1]
    assert snapshot.current_actions[0].payload['items'] == [1]
    state.events[0].payload['items'].append(4)
    state.current_actions[0].payload['items'].append(5)
    assert snapshot.events[0].payload['items'] == [1]
    assert snapshot.current_actions[0].payload['items'] == [1]


def test_surface_client_refreshes_readonly_view_after_delivery():
    from src.simulation.ui_testing.fixtures import RecordingClient
    from src.simulation.ui_testing.surface import _CurrentClientState

    state = GameState()
    client = RecordingClient(state)
    client.enable_client_view(presentation_values())
    current = _CurrentClientState(client)
    assert isinstance(client.get_state(), ClientGameStateView)
    assert current.client_presentation
    client.deliver_event('Example', {'items': [1]}, 'event-1')
    assert current.journal.domain_events[0]['payload']['items'] == (1,)
    assert state.journal.domain_events[0]['payload']['items'] == [1]
    client.deliver_snapshot({'globals': {'changed': ['snapshot']}})
    assert current.globals['changed'] == ('snapshot',)
    assert isinstance(client.get_state(), ClientGameStateView)


def test_typed_random_event_is_visible_in_snapshot():
    state = GameState(tables={
        'regions': pl.DataFrame({'id': [7], 'name': ['Odesa'], 'owner': ['UKR']}),
        'random_event_instances': pl.DataFrame([{
            'id': 'epidemic', 'event_type': 'epidemic', 'label': 'Epidemic',
            'region_id': 7, 'status': 'active', 'triggered_at_minute': 10,
            'expires_at_minute': 100, 'severity': 0.4,
        }]),
    })
    items = EventFeedPresenter().items(view(state))
    assert any(item.id == 'instance:epidemic' and item.headline == 'Epidemic' for item in items)
