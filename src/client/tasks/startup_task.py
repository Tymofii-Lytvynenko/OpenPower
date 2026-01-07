from src.shared.config import GameConfig
from src.server.session import GameSession

class StartupTask:
    """
    Acts as an adapter between the generic LoadingView (UI) and the GameSession (Server).
    
    Implements:
        The 'LoadingTask' Protocol (duck typing).
        
    Responsibilities:
        - Holds the state needed by the LoadingView (progress, status_text).
        - Triggers the server creation process in a way that allows progress monitoring.
    """

    def __init__(self, config: GameConfig):
        self.config = config
        
        # Interface properties required by LoadingView
        self.progress: float = 0.0
        self.status_text: str = "Initializing launcher..."

    def run(self) -> GameSession:
        """
        Executed in a background thread by LoadingView.
        """
        # We delegate the actual work to the Session's factory method.
        # We pass 'self._on_server_progress' so the server can update OUR state,
        # which the LoadingView reads every frame.
        session = GameSession.create_local(self.config, self._on_server_progress)
        
        return session

    def _on_server_progress(self, p: float, text: str):
        """
        Callback used by the server to report status.
        Updates the local state, which is read by the main UI thread.
        """
        self.progress = p
        self.status_text = text