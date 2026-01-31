from abc import ABC, abstractmethod
from typing import Dict, Tuple
from src.server.state import GameState

class BaseMapMode(ABC):
    """
    Strategy interface for coloring the map.
    Returns a mapping of Region ID -> RGB Color.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def calculate_colors(self, state: GameState) -> Dict[int, Tuple[int, int, int]]:
        """
        Pure data transformation.
        Input: State (Polars DataFrames)
        Output: Dictionary mapping Region Real IDs to Tuple (R, G, B)
        """
        pass