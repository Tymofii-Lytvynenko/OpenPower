from abc import ABC, abstractmethod
from typing import Dict, Tuple
from src.server.state import GameState

class BaseMapMode(ABC):
    """
    Strategy interface for coloring the map.
    Separates data calculation from 3D presentation attributes.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Display name for the UI."""
        pass

    @property
    def overlay_enabled(self) -> bool:
        """
        If True, the renderer will blend the calculated colors over the terrain.
        If False, only the terrain is shown (useful for 'Terrain Only' mode).
        """
        return True

    @property
    def opacity(self) -> float:
        """
        Opacity of the color overlay (0.0 to 1.0).
        Can be overridden by subclasses for specific visual effects.
        """
        return 0.90

    @abstractmethod
    def calculate_colors(self, state: GameState) -> Dict[int, Tuple[int, int, int]]:
        """
        Pure data transformation.
        Input: State (Polars DataFrames)
        Output: Dictionary mapping Region Real IDs to Tuple (R, G, B)
        """
        pass