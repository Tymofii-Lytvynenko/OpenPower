from src.shared.mod_api import mod

from modules.base.schema import BASE_TABLE_SCHEMAS
from modules.base.systems.demographics.population_system import PopulationSystem
from modules.base.systems.economy.budget_system import BudgetSystem
from modules.base.systems.economy.diplomatic_aid_system import DiplomaticAidSystem
from modules.base.systems.economy.internal_economy_system import InternalEconomySystem
from modules.base.systems.economy.trade_system import TradeSystem
from modules.base.systems.military.combat_system import CombatSystem
from modules.base.systems.military.military_system import MilitarySystem
from modules.base.systems.military.research_program_system import ResearchProgramSystem
from modules.base.systems.politics.politics_system import PoliticsSystem
from modules.base.systems.world.ai_system import AISystem
from modules.base.systems.world.bootstrap_system import BootstrapSystem
from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from modules.base.systems.world.random_events_system import RandomEventsSystem
from modules.base.systems.world.territory_system import TerritorySystem
from modules.base.systems.world.time_system import TimeSystem


def contribute():
    return mod(
        TimeSystem,
        BootstrapSystem,
        DiplomacySystem,
        PoliticsSystem,
        PopulationSystem,
        MilitarySystem,
        ResearchProgramSystem,
        CombatSystem,
        TerritorySystem,
        AISystem,
        RandomEventsSystem,
        TradeSystem,
        InternalEconomySystem,
        BudgetSystem,
        DiplomaticAidSystem,
        schemas=BASE_TABLE_SCHEMAS,
    )
