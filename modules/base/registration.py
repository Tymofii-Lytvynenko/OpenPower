from typing import List
from src.engine.interfaces import ISystem

# We import the systems that belong to this module

def register() -> List[ISystem]:
    """
    The ModManager calls this function to discover what logic 
    this module contributes to the game loop.
    """
    return [
        # Order in this list doesn't matter anymore!
        # The Engine sorts them automatically based on their .dependencies property.
        #TerritorySystem(),
        #EconomySystem()
    ]