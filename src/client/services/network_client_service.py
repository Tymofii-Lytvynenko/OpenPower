from typing import TYPE_CHECKING
from src.shared.actions import GameAction

if TYPE_CHECKING:
    from src.server.session import GameSession
    from src.server.state import GameState

class NetworkClient:
    """
    The Bridge between the Client View (UI) and the Server Session.
    Enforces the 'Passive Observer' rule by providing read-only access to state
    and a write-only channel for Actions.
    """
    
    def __init__(self, session: "GameSession"):
        self.session = session
        # In a real networked game, this ID comes from the handshake
        self.player_id = "local_admin" 

    def send_action(self, action: GameAction):
        """
        Sends an intent to the server.
        The client NEVER applies this action locally. It waits for the 
        server to process it and send back a new State.
        """
        action.player_id = self.player_id
        self.session.receive_action(action)

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