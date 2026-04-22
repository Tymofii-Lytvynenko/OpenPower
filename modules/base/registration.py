from typing import List
from src.engine.interfaces import ISystem

# Import Systems
from modules.base.systems.time_system import TimeSystem
from modules.base.systems.politics_system import PoliticsSystem
from modules.base.systems.population_system import PopulationSystem
from modules.base.systems.military_system import MilitarySystem
from modules.base.systems.territory_system import TerritorySystem
from modules.base.systems.ai_system import AISystem
from modules.base.systems.trade_system import TradeSystem
from modules.base.systems.economy_system import EconomySystem
from modules.base.systems.budget_system import BudgetSystem

def register() -> List[ISystem]:
    """
    The ModManager calls this function to discover what logic 
    this module contributes to the game loop.
    """
    return [
        TimeSystem(),
        PoliticsSystem(),
        PopulationSystem(),
        MilitarySystem(),
        TerritorySystem(),
        AISystem(),
        TradeSystem(),
        EconomySystem(),
        BudgetSystem()
    ]