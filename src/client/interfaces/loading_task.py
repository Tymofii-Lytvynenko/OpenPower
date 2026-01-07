from typing import Protocol, Any

class LoadingTask(Protocol):
    """
    Interface for any long-running operation that needs a UI.
    """
    progress: float      # 0.0 to 1.0
    status_text: str     # Current step description
    
    def run(self) -> Any:
        """
        The heavy blocking function. 
        Returns data to be passed to the next view.
        """
        ...