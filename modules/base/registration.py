from src.shared.mod_api import mod

from modules.base.schema import BASE_TABLE_SCHEMAS
from modules.base.systems.demographics.population_system import PopulationSystem
from modules.base.systems.demographics.migration_system import MigrationSystem
from modules.base.systems.economy.budget_system import BudgetSystem
from modules.base.systems.economy.diplomatic_aid_system import DiplomaticAidSystem
from modules.base.systems.economy.economic_health_system import EconomicHealthSystem
from modules.base.systems.economy.internal_economy_system import InternalEconomySystem
from modules.base.systems.economy.trade_system import TradeSystem
from modules.base.systems.military.combat_system import CombatSystem
from modules.base.systems.military.capability_system import MilitaryCapabilitySystem
from modules.base.systems.military.battle_strategy_system import BattleStrategySystem
from modules.base.systems.military.covert_operations_system import CovertOperationsSystem
from modules.base.systems.military.foreign_order_system import ForeignOrderSystem
from modules.base.systems.military.military_system import MilitarySystem
from modules.base.systems.military.research_program_system import ResearchProgramSystem
from modules.base.systems.military.strategic_warfare_system import StrategicWarfareSystem
from modules.base.systems.politics.politics_system import PoliticsSystem
from modules.base.systems.politics.political_lifecycle_system import PoliticalLifecycleSystem
from modules.base.systems.politics.identity_policy_system import IdentityPolicySystem
from modules.base.systems.world.ai_system import AISystem
from modules.base.systems.world.bootstrap_system import BootstrapSystem
from modules.base.systems.world.campaign_system import CampaignSetupSystem, CampaignSystem
from modules.base.systems.world.history_system import HistorySystem
from modules.base.systems.world.infrastructure_system import InfrastructureSystem
from modules.base.systems.world.advanced_diplomacy_system import AdvancedDiplomacySystem
from modules.base.systems.world.bilateral_trade_system import BilateralTradeSystem
from modules.base.systems.world.diplomatic_balance_system import DiplomaticBalanceSystem
from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from modules.base.systems.world.random_events_system import RandomEventsSystem
from modules.base.systems.world.recognition_system import RecognitionSystem
from modules.base.systems.world.territory_system import TerritorySystem
from modules.base.systems.world.time_system import TimeSystem


def contribute():
    return mod(
        TimeSystem,
        BootstrapSystem,
        CampaignSetupSystem,
        CampaignSystem,
        HistorySystem,
        AdvancedDiplomacySystem,
        DiplomacySystem,
        DiplomaticBalanceSystem,
        RecognitionSystem,
        IdentityPolicySystem,
        PoliticsSystem,
        PoliticalLifecycleSystem,
        PopulationSystem,
        MigrationSystem,
        MilitarySystem,
        BattleStrategySystem,
        MilitaryCapabilitySystem,
        ResearchProgramSystem,
        CombatSystem,
        CovertOperationsSystem,
        StrategicWarfareSystem,
        InfrastructureSystem,
        TerritorySystem,
        AISystem,
        RandomEventsSystem,
        BilateralTradeSystem,
        TradeSystem,
        ForeignOrderSystem,
        InternalEconomySystem,
        BudgetSystem,
        EconomicHealthSystem,
        DiplomaticAidSystem,
        schemas=BASE_TABLE_SCHEMAS,
    )
