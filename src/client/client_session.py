import multiprocessing as mp
from typing import Optional

from src.server.state import GameState
from src.shared.actions import GameAction
from src.server.server_process import run_server_process

class ClientSessionProxy:
    """
    A proxy object that lives in the main UI thread.
    It handles communication with the background Simulation Process.
    """
    
    def __init__(self, config_root):
        # Create Communication Pipes
        self.action_queue = mp.Queue()
        self.state_queue = mp.Queue()
        self.progress_queue = mp.Queue()
        
        self.state: Optional[GameState] = None
        
        # Spawn the Background Process
        self.process = mp.Process(
            target=run_server_process,
            args=(config_root, self.action_queue, self.state_queue, self.progress_queue),
            daemon=True # Ensures process dies if window is closed abruptly
        )
        self.process.start()

    def receive_action(self, action: GameAction):
        """Sends an action to the background server."""
        self.action_queue.put(action)

    def tick(self, delta_time: float):
        """
        Called by the Window. Instead of calculating math, 
        it just grabs the latest pre-calculated state from the server.
        """
        try:
            # Drain queue to get the absolute latest state
            latest_ipc = None
            while not self.state_queue.empty():
                latest_ipc = self.state_queue.get_nowait()
                
            if latest_ipc:
                self.state = GameState.from_ipc(latest_ipc)
        except Exception:
            pass

    def get_state_snapshot(self) -> Optional[GameState]:
        return self.state

    def shutdown(self):
        self.action_queue.put("SHUTDOWN")
        self.process.join(timeout=2.0)
        if self.process.is_alive():
            self.process.terminate()