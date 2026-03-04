"""
eco_engine.py

A modular library for estimating internal economic production and consumption
based on trade data (BACI), GDP, and Population.
(Is not adapted for game logic yet)

Design Principles:
- Composition over Inheritance (CoI)
- Data-Oriented Design (DTOs separate from Logic)
- Strategy Pattern for Consumption Logic

Usage:
    See the 'if __name__ == "__main__":' block for a complete example.
"""

from dataclasses import dataclass, field
from typing import Dict, Protocol, Optional, Literal
from enum import Enum

# --- 1. Data Structures (DTOs) ---

class SectorCategory(Enum):
    """
    Classifies economic sectors to adjust consumption elasticity.
    """
    BASIC = "basic"       # Food, raw materials (inelastic demand)
    INDUSTRIAL = "ind"    # Machinery, chemicals (linear demand)
    LUXURY = "luxury"     # Electronics, high-end goods (elastic demand)
    SERVICE = "service"   # Non-tradable (often not in BACI, but good to have)


@dataclass(frozen=True)
class EconomicProfile:
    """
    Represents the macroeconomic state of a country.
    
    Attributes:
        gdp_ppp (float): Purchasing Power Parity GDP in USD.
        population (int): Total population count.
    """
    gdp_ppp: float
    population: int

    @property
    def gdp_per_capita(self) -> float:
        """Safe calculation of GDP per capita."""
        if self.population == 0:
            return 0.0
        return self.gdp_ppp / self.population


@dataclass(frozen=True)
class TradeData:
    """
    Represents external trade flows for a specific sector.
    """
    sector_id: str
    export_value: float
    import_value: float

    @property
    def net_exports(self) -> float:
        return self.export_value - self.import_value


@dataclass(frozen=True)
class SectorConfig:
    """
    Configuration for a specific economic sector.
    
    Attributes:
        global_weight (float): The sector's share of total WORLD trade (0.0 to 1.0).
        category (SectorCategory): The elasticity category for this sector.
    """
    sector_id: str
    global_weight: float
    category: SectorCategory = SectorCategory.INDUSTRIAL


@dataclass(frozen=True)
class CalculatedSector:
    """
    The final output for a sector.
    """
    sector_id: str
    production: float
    consumption: float
    imports: float
    exports: float


# --- 2. Interfaces (Protocols) ---

class ConsumptionStrategy(Protocol):
    """
    Interface for estimating internal consumption.
    Different algorithms can be swapped in here without changing the core engine.
    """
    def estimate(
        self, 
        market_size: float, 
        profile: EconomicProfile, 
        config: SectorConfig
    ) -> float:
        ...


# --- 3. Implementations (Logic) ---

class GlobalBasketStrategy:
    """
    Estimates consumption based on the 'Global Basket Proxy' method.
    
    It assumes that a country's consumption structure roughly mirrors the 
    global trade structure, adjusted for the country's wealth (GDP/capita).
    """
    
    def __init__(self, world_avg_gdp_capita: float = 12000.0):
        self.world_avg_gdp_capita = world_avg_gdp_capita

    def estimate(
        self, 
        market_size: float, 
        profile: EconomicProfile, 
        config: SectorConfig
    ) -> float:
        # Base demand is purely the market size distributed by global weights
        base_demand = market_size * config.global_weight

        # Adjust for wealth (GDP per capita)
        wealth_ratio = profile.gdp_per_capita / self.world_avg_gdp_capita
        
        # Apply modifiers based on sector category (Engel's Law approximation)
        modifier = 1.0
        
        if config.category == SectorCategory.BASIC:
            # Poorer nations spend a larger % of income on basics
            if wealth_ratio < 1.0:
                modifier = 1.5 - (wealth_ratio * 0.5)
            else:
                 # Wealthier nations spend proportionally less on basics
                modifier = max(0.8, 1.0 - (wealth_ratio * 0.05))
                
        elif config.category == SectorCategory.LUXURY:
            # Demand for luxury scales faster than income
            modifier = wealth_ratio ** 1.1

        return base_demand * modifier


class EconomyCalculator:
    """
    The main engine. It coordinates data and strategies to produce results.
    It is stateless regarding the data it processes.
    """
    
    def __init__(self, consumption_strategy: ConsumptionStrategy):
        # We inject the strategy (Dependency Injection) for modularity.
        self._strategy = consumption_strategy

    def calculate_internal_market(
        self, 
        profile: EconomicProfile, 
        trade_flows: list[TradeData]
    ) -> float:
        """
        Calculates the total available internal money (The Wallet).
        D = GDP - (TotalExports - TotalImports)
        """
        total_exports = sum(t.export_value for t in trade_flows)
        total_imports = sum(t.import_value for t in trade_flows)
        
        # We clamp at 0 because a market cannot have negative size, 
        # even if trade deficit is massive (which is usually covered by debt).
        return max(0.0, profile.gdp_ppp - (total_exports - total_imports))

    def process_sector(
        self,
        market_size: float,
        profile: EconomicProfile,
        trade: TradeData,
        config: SectorConfig
    ) -> CalculatedSector:
        """
        Calculates Production and Consumption for a single sector.
        """
        # 1. Estimate Consumption (C) using the injected strategy
        estimated_consumption = self._strategy.estimate(market_size, profile, config)
        
        # 2. Calculate Production (P)
        # Identity: P + M = C + E  =>  P = C + E - M
        production = estimated_consumption + trade.export_value - trade.import_value
        
        # 3. Validation & Correction (The "Clamp")
        # If P < 0, it means our estimated consumption was too low given the 
        # massive imports. We must assume the country consumes everything it imports.
        if production < 0:
            production = 0.0
            # Recalculate C to satisfy the identity P=0 => C = M - E
            # (assuming re-export is handled or C absorbs the net import)
            estimated_consumption = max(0.0, trade.import_value - trade.export_value)

        return CalculatedSector(
            sector_id=trade.sector_id,
            production=production,
            consumption=estimated_consumption,
            imports=trade.import_value,
            exports=trade.export_value
        )

    def compute_national_economy(
        self,
        profile: EconomicProfile,
        trade_data: Dict[str, TradeData],
        sector_configs: Dict[str, SectorConfig]
    ) -> Dict[str, CalculatedSector]:
        """
        Batch processes an entire country's economy.
        """
        # 1. Calculate the total size of the internal pie
        market_size = self.calculate_internal_market(profile, list(trade_data.values()))
        
        results = {}
        
        # 2. Iterate through known sectors
        for sector_id, config in sector_configs.items():
            trade = trade_data.get(
                sector_id, 
                TradeData(sector_id, 0.0, 0.0) # Default to 0 trade if missing
            )
            
            result = self.process_sector(market_size, profile, trade, config)
            results[sector_id] = result
            
        return results


# --- 4. Usage Example ---

if __name__ == "__main__":
    # --- Setup Configuration (Static Data) ---
    # In a real app, these "weights" come from analyzing the full BACI dataset once.
    configs = {
        "1001": SectorConfig("1001", global_weight=0.05, category=SectorCategory.BASIC),       # Wheat
        "2709": SectorConfig("2709", global_weight=0.10, category=SectorCategory.BASIC),       # Crude Oil
        "8542": SectorConfig("8542", global_weight=0.15, category=SectorCategory.LUXURY),      # Microchips
        "8703": SectorConfig("8703", global_weight=0.08, category=SectorCategory.INDUSTRIAL),  # Cars
    }

    # --- Setup Country Data (Dynamic Data) ---
    # Example: Ukraine-ish stats
    ukraine_profile = EconomicProfile(
        gdp_ppp=160_000_000_000.0,  # 160 Billion
        population=38_000_000
    )

    ukraine_trade = {
        "1001": TradeData("1001", export_value=5_000_000_000, import_value=10_000_000), # Huge export
        "2709": TradeData("2709", export_value=0, import_value=3_000_000_000),          # Huge import
        "8542": TradeData("8542", export_value=50_000_000, import_value=500_000_000),   # Net import
        "8703": TradeData("8703", export_value=100_000_000, import_value=2_000_000_000),# Net import
    }

    # --- Execution ---
    # 1. Initialize Strategy
    strategy = GlobalBasketStrategy(world_avg_gdp_capita=12000.0)
    
    # 2. Initialize Engine
    engine = EconomyCalculator(strategy)
    
    # 3. Compute
    results = engine.compute_national_economy(ukraine_profile, ukraine_trade, configs)

    # --- Output ---
    print(f"{'Sector':<10} | {'Production ($)':<20} | {'Consumption ($)':<20} | {'Type':<10}")
    print("-" * 70)
    
    for sector_id, res in results.items():
        cat = configs[sector_id].category.name
        print(f"{sector_id:<10} | {res.production:,.0f}<20 | {res.consumption:,.0f}<20 | {cat:<10}")

    # Expected Logic Checks:
    # Wheat (1001): High Production (covers massive export + domestic food needs)
    # Oil (2709): Zero Production (Import covers Consumption)