from typing import List
from src.engine.interfaces import ISystem

# Import Systems
from modules.base.systems.world.time_system import TimeSystem
from modules.base.systems.politics.politics_system import PoliticsSystem
from modules.base.systems.demographics.population_system import PopulationSystem
from modules.base.systems.military.military_system import MilitarySystem
from modules.base.systems.world.territory_system import TerritorySystem
from modules.base.systems.world.ai_system import AISystem
from modules.base.systems.economy.trade_system import TradeSystem
from modules.base.systems.economy.economy_system import EconomySystem
from modules.base.systems.economy.budget_system import BudgetSystem

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