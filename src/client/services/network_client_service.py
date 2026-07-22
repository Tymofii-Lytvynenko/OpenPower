from dataclasses import replace
from typing import TYPE_CHECKING
from src.shared.actions import GameAction

if TYPE_CHECKING:
    from src.shared.protocols import SessionPort
    from src.shared.state import GameState

class NetworkClient:
    """
    The Bridge between the Client View (UI) and the Server Session.
    Enforces the 'Passive Observer' rule by providing read-only access to state
    and a write-only channel for Actions.
    """
    
    def __init__(self, session: "SessionPort"):
        self.session = session
        # In a real networked game, this ID comes from the handshake
        self.player_id = "local_admin" 

    def get_system_errors(self) -> list:
        if hasattr(self.session, "system_errors"):
            return self.session.system_errors
        return []

    def clear_system_errors(self) -> None:
        if hasattr(self.session, "system_errors"):
            self.session.system_errors.clear() 

    def send_action(self, action: GameAction) -> str:
        """
        Sends an intent to the server.
        The client NEVER applies this action locally. It waits for the 
        server to process it and send back a new State.
        """
        authoritative_action = replace(action, player_id=self.player_id)
        return self.session.receive_action(authoritative_action)

    def get_state(self) -> "GameState":
        """
        Fetches the latest authoritative world state.
        """
        return self.session.get_state_snapshot()

    def request_save(self, is_editor: bool = False):
        """Saves gameplay state or editor state depending on the context."""
        if is_editor:
            print("[NetworkClient] Requesting server to save map data...")
            self.session.save_map_changes()
        else:
            print("[NetworkClient] Requesting server to save gameplay state...")
            from src.shared.actions import ActionSaveGame
            self.send_action(ActionSaveGame(player_id=self.player_id, save_name="quicksave"))