from functools import lru_cache

import numpy as np
import polars as pl
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE, SYSTEM_STATE_HELPER
from src.shared.state import GameState
from src.shared.events import EventRealSecond
from modules.base.systems.economy.treaty_trade_policy import TreatyTradePolicy
from modules.base.systems.economy.market_input_validator import MarketInputValidator
from modules.base.systems.economy.market_frame_builder import MarketFrameBuilder
from modules.base.systems.economy.dataframe_market_simulator import (
    DataFrameMarketSimulator,
)
from modules.base.systems.economy.missing_column_warning_registry import (
    MissingColumnWarningRegistry,
)
from modules.base.systems.economy.market_data import _MarketIndexCache
from modules.base.systems.economy.unconstrained_market_simulator import (
    UnconstrainedMarketSimulator,
)
from modules.base.systems.world.recognition_policy import regional_trade_access_allowed


class TradeSystem(ISystem):
    """
    Simulates Global Market Clearing with Physical Constraints.
    Features: Service Evaporation, Asset Depreciation, and Organic Market Pressure.
    """

    access = SystemAccess(
        reads=frozenset({
            'countries', 'domestic_production', 'countries_treaties', 'treaty_effects',
            'resource_ledger', 'stockpiles', 'regional_production', 'regions',
            'recognition_cases', 'regional_recognition_status',
        }),
        writes=frozenset({'countries', 'domestic_production', 'resource_ledger', 'stockpiles', 'trade_network'}),
        phase=SystemPhase.TRADE,
    )

    runtime_state_contract = {
        "_missing_columns": SYSTEM_STATE_CACHE,
        "_market_index_cache": SYSTEM_STATE_CACHE,
        "_treaty_trade_policy": SYSTEM_STATE_HELPER,
        "_market_input_validator": SYSTEM_STATE_HELPER,
        "_market_frame_builder": SYSTEM_STATE_HELPER,
        "_unconstrained_market_simulator": SYSTEM_STATE_HELPER,
        "_dataframe_market_simulator": SYSTEM_STATE_HELPER,
        "_market_column_warning_registry": SYSTEM_STATE_HELPER,
    }

    TRADE_PRIORITY_MATRIX = {
        "cereals": 10, "vegetables_and_fruits": 11, "meat_and_fish": 12, "dairy": 13, 
        "pharmaceuticals": 14, "health_services": 15, "electricity": 20, "fossil_fuels": 21, 
        "transport_services": 22, "minerals": 30, "iron_and_steel": 31, "chemicals": 32, 
        "wood_and_paper": 33, "plastics_and_rubber": 34, "machinery_and_instruments": 40, 
        "industrial_services": 41, "construction_services": 42, "construction_materials": 43, 
        "vehicles": 44, "commodities": 50, "fabrics_and_leather": 51, "appliances": 52, 
        "business_services": 53, "it_and_telecom_services": 54, "tobacco": 60, 
        "drugs_and_raw_plants": 61, "recreational_services": 62, "tourism_services": 63, 
        "luxury_commodities": 64, "precious_stones": 65, "non_ferrous_metals": 66, 
        "arms_and_ammunition": 67, "education_services": 68, "government_services": 69, 
        "financial_services": 70, "other_food_and_beverages": 71
    }

    # Physical properties of resources: Can they be stored? How quickly do they depreciate/spoil per year?
    RESOURCE_PHYSICS = {
        # Services and energy: CANNOT be stored. They are consumed instantly.
        "electricity": {"is_storable": False, "decay_rate": 1.0},
        "construction_services": {"is_storable": False, "decay_rate": 1.0},
        "industrial_services": {"is_storable": False, "decay_rate": 1.0},
        "health_services": {"is_storable": False, "decay_rate": 1.0},
        "recreational_services": {"is_storable": False, "decay_rate": 1.0},
        "business_services": {"is_storable": False, "decay_rate": 1.0},
        "transport_services": {"is_storable": False, "decay_rate": 1.0},
        "education_services": {"is_storable": False, "decay_rate": 1.0},
        "government_services": {"is_storable": False, "decay_rate": 1.0},
        "financial_services": {"is_storable": False, "decay_rate": 1.0},
        "it_and_telecom_services": {"is_storable": False, "decay_rate": 1.0},
        "tourism_services": {"is_storable": False, "decay_rate": 1.0},

        # Fast depreciation (Finished goods, 20-25% per year due to aging/fashion)
        "appliances": {"is_storable": True, "decay_rate": 0.20},
        "vehicles": {"is_storable": True, "decay_rate": 0.25},
        "machinery_and_instruments": {"is_storable": True, "decay_rate": 0.20},
        "commodities": {"is_storable": True, "decay_rate": 0.25},
        "luxury_commodities": {"is_storable": True, "decay_rate": 0.20},
        "pharmaceuticals": {"is_storable": True, "decay_rate": 0.15}, # Expiry date / Shelf life
        "arms_and_ammunition": {"is_storable": True, "decay_rate": 0.10}, 

        # Medium spoilage (Food and Agro, 10-15% annual losses)
        "cereals": {"is_storable": True, "decay_rate": 0.10},
        "vegetables_and_fruits": {"is_storable": True, "decay_rate": 0.15},
        "meat_and_fish": {"is_storable": True, "decay_rate": 0.15},
        "dairy": {"is_storable": True, "decay_rate": 0.15},
        "tobacco": {"is_storable": True, "decay_rate": 0.10},
        "drugs_and_raw_plants": {"is_storable": True, "decay_rate": 0.10},
        "other_food_and_beverages": {"is_storable": True, "decay_rate": 0.10},

        # Slow spoilage (Raw materials and Materials, 2-5% per year)
        "fossil_fuels": {"is_storable": True, "decay_rate": 0.05}, # Evaporation, leakage
        "wood_and_paper": {"is_storable": True, "decay_rate": 0.05},
        "minerals": {"is_storable": True, "decay_rate": 0.02},
        "iron_and_steel": {"is_storable": True, "decay_rate": 0.03}, # Rust
        "precious_stones": {"is_storable": True, "decay_rate": 0.00}, # Eternal
        "non_ferrous_metals": {"is_storable": True, "decay_rate": 0.02},
        "fabrics_and_leather": {"is_storable": True, "decay_rate": 0.05},
        "plastics_and_rubber": {"is_storable": True, "decay_rate": 0.05},
        "chemicals": {"is_storable": True, "decay_rate": 0.08},
        "construction_materials": {"is_storable": True, "decay_rate": 0.05},
    }

    def __init__(
        self,
        market_input_validator: MarketInputValidator | None = None,
        market_frame_builder: MarketFrameBuilder | None = None,
        unconstrained_market_simulator: UnconstrainedMarketSimulator | None = None,
        market_column_warning_registry: MissingColumnWarningRegistry | None = None,
        dataframe_market_simulator: DataFrameMarketSimulator | None = None,
    ):
        self._market_column_warning_registry = (
            market_column_warning_registry
            if market_column_warning_registry is not None
            else MissingColumnWarningRegistry(self.id)
        )
        self._treaty_trade_policy = TreatyTradePolicy()
        self._market_input_validator = (
            market_input_validator if market_input_validator is not None else MarketInputValidator()
        )
        self._market_frame_builder = (
            market_frame_builder if market_frame_builder is not None else MarketFrameBuilder()
        )
        self._unconstrained_market_simulator = (
            unconstrained_market_simulator
            if unconstrained_market_simulator is not None
            else UnconstrainedMarketSimulator()
        )
        self._dataframe_market_simulator = (
            dataframe_market_simulator
            if dataframe_market_simulator is not None
            else DataFrameMarketSimulator.create_default(
                self._market_input_validator,
                self._market_frame_builder,
                self._treaty_trade_policy,
                regional_trade_access_allowed,
            )
        )

    @property
    def _missing_columns(self) -> set[str]:
        return self._market_column_warning_registry.seen_columns

    @_missing_columns.setter
    def _missing_columns(self, value: set[str]) -> None:
        self._market_column_warning_registry.seen_columns = value

    @property
    def _market_index_cache(self) -> _MarketIndexCache | None:
        return self._unconstrained_market_simulator.market_index_cache

    @_market_index_cache.setter
    def _market_index_cache(self, value: _MarketIndexCache | None) -> None:
        self._unconstrained_market_simulator.market_index_cache = value

    @property
    def id(self) -> str:
        return "base.trade"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.diplomacy"]

    def update(self, state: GameState, delta_time: float) -> None:
        real_sec_events = [e for e in state.events if isinstance(e, EventRealSecond)]
        for event in real_sec_events:
            if event.is_paused or event.game_seconds_passed <= 0:
                continue
            fraction = event.game_seconds_passed / (365.25 * 24 * 3600)
            self._simulate_market_cycle(state, fraction)

    def _simulate_market_cycle(self, state: GameState, fraction: float):
        if "countries" not in state.tables or "domestic_production" not in state.tables:
            return
        if not np.isfinite(fraction) or fraction < 0.0:
            raise ValueError("Trade elapsed-year fraction must be finite and non-negative.")
        if self._simulate_market_cycle_fast(state, fraction):
            return
        self._dataframe_market_simulator.simulate(
            state,
            fraction,
            _resource_physics_table(),
            self._market_column_warning_registry,
        )

    def _simulate_market_cycle_fast(self, state: GameState, fraction: float) -> bool:
        """Delegate eligible unconstrained cycles to the composed NumPy simulator."""
        return self._unconstrained_market_simulator.simulate(
            state=state,
            fraction=fraction,
            resource_physics=self.RESOURCE_PHYSICS,
            warning_registry=self._market_column_warning_registry,
        )

    def _apply_treaty_production_bonus(
        self,
        state: GameState,
        production: pl.LazyFrame,
    ) -> pl.LazyFrame:
        return self._dataframe_market_simulator.apply_treaty_production_bonus(
            state,
            production,
        )

    def _apply_constrained_flows(
        self,
        market: pl.DataFrame,
        flows: pl.DataFrame,
        fraction: float,
    ) -> pl.DataFrame:
        return self._dataframe_market_simulator.apply_constrained_flows(
            market,
            flows,
            fraction,
        )

    def _countries_from_constrained_market(
        self,
        state: GameState,
        market: pl.DataFrame,
    ) -> pl.DataFrame:
        return self._dataframe_market_simulator.countries_from_constrained_market(
            state,
            market,
        )


@lru_cache(maxsize=1)
def _resource_physics_table() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "game_resource_id": resource_id,
                "is_storable": values["is_storable"],
                "decay_rate": values["decay_rate"],
            }
            for resource_id, values in TradeSystem.RESOURCE_PHYSICS.items()
        ]
    )
