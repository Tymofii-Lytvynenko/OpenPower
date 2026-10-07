from __future__ import annotations

from dataclasses import dataclass

from src.client.interfaces.loading import LoadingTask
from src.client.interfaces.session_factory import ClientSessionPort, SessionFactory
from src.client.services.network_client_service import NetworkClient
from src.shared.actions import ActionSetPaused
from src.shared.config import GameConfig
from src.shared.protocols import SessionPort


@dataclass
class PassiveSession:
    received: list[object]

    def receive_action(self, action):
        self.received.append(action)
        return "cmd-1"

    def get_state_snapshot(self):
        return None

    def save_map_changes(self):
        pass

    @property
    def progress_queue(self):
        return object()

    @property
    def map_data(self):
        return object()

    def tick(self, delta_time: float) -> None:
        pass

    def shutdown(self) -> None:
        pass


@dataclass
class SimpleLoadingTask:
    progress: float = 0.0
    status_text: str = "Waiting"

    def run(self):
        return "result"

    def cancel(self):
        pass


def test_loading_task_contract_includes_cooperative_cancellation() -> None:
    assert isinstance(SimpleLoadingTask(), LoadingTask)


def test_session_ports_forward_commands_without_mutating_local_state() -> None:
    session = PassiveSession([])
    assert isinstance(session, SessionPort)
    assert isinstance(session, ClientSessionPort)
    action = ActionSetPaused(player_id="USA", is_paused=True)

    assert session.receive_action(action) == "cmd-1"
    assert session.received == [action]
    assert session.get_state_snapshot() is None


def test_session_factory_contract_accepts_config_and_optional_startup_context() -> None:
    created = []

    def factory(config: GameConfig, *, save_name=None, player_tag=None):
        created.append((config, save_name, player_tag))
        return PassiveSession([])

    assert isinstance(factory, SessionFactory)
    config = object()
    factory(config, save_name="campaign", player_tag="USA")
    assert created == [(config, "campaign", "USA")]


def test_network_client_forwards_intents_and_reads_the_same_authoritative_snapshot() -> None:
    state = object()

    class Session(PassiveSession):
        def get_state_snapshot(self):
            return state

    session = Session([])
    client = NetworkClient(session)
    action = ActionSetPaused(player_id="USA", is_paused=True)

    command_id = client.send_action(action)

    assert command_id == "cmd-1"
    assert session.received == [ActionSetPaused(player_id="local_admin", is_paused=True)]
    assert client.get_state() is state
