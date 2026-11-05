from functools import lru_cache

import numpy as np
import polars as pl
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE, SYSTEM_STATE_HELPER
from src.shared.state import GameState
from src.shared.numeric import stable_group_sums, stable_sum
from src.shared.frames import ensure_sorted
from src.shared.events import EventRealSecond
from modules.base.systems.economy.treaty_trade_policy import TreatyTradePolicy
from modules.base.systems.economy.market_input_validator import MarketInputValidator
from modules.base.systems.economy.market_frame_builder import MarketFrameBuilder
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
            if event.is_paused or event.game_seconds_passed <= 0: continue
            fraction = event.game_seconds_passed / (365.25 * 24 * 3600)
            self._simulate_market_cycle(state, fraction)

    def _simulate_market_cycle(self, state: GameState, fraction: float):
        if "countries" not in state.tables or "domestic_production" not in state.tables: return
        if not np.isfinite(fraction) or fraction < 0.0:
            raise ValueError("Trade elapsed-year fraction must be finite and non-negative.")
        if self._simulate_market_cycle_fast(state, fraction):
            return

        # Invalid quantities otherwise contaminate global ratios and every country's closing stock.
        self._market_input_validator.validate(state)

        production = state.get_table("domestic_production")
        production_lf = self._apply_treaty_production_bonus(state, production.lazy())
        market_lf = self._market_frame_builder.build(
            state,
            production_lf,
            _resource_physics_table(),
            self._market_column_warning_registry,
        )

        # ---------------------------------------------------------
        # Local Supply & Trade Desires
        # ---------------------------------------------------------
        market_lf = market_lf.with_columns(
            (pl.col("domestic_production") + pl.col("stock_amount")).alias("local_supply")
        )

        market_lf = market_lf.with_columns([
            pl.when(pl.col("local_supply") >= pl.col("demand")).then(pl.col("local_supply") - pl.col("demand")).otherwise(0.0).alias("export_desired"),
            pl.when(pl.col("demand") > pl.col("local_supply")).then(pl.col("demand") - pl.col("local_supply")).otherwise(0.0).alias("import_desired")
        ])

        market_lf = market_lf.with_columns(
            (pl.col("import_desired") * pl.col("_economic_trade_modifier")).alias("affordable_import")
        )

        # ---------------------------------------------------------
        # Global Market Clearing
        # ---------------------------------------------------------
        world_market_lf = market_lf.group_by("game_resource_id").agg(
            stable_sum("export_desired").alias("global_supply"),
            stable_sum("affordable_import").alias("global_demand"),
        )

        market_lf = market_lf.join(
            world_market_lf, on="game_resource_id", how="left"
        )
        market_lf = market_lf.with_columns(
            (
                pl.col("affordable_import")
                * pl.when(pl.col("global_demand") > 0)
                .then(pl.min_horizontal(1.0, pl.col("global_supply") / pl.col("global_demand")))
                .otherwise(0.0)
            ).alias("import_actual"),
            (
                pl.col("export_desired")
                * pl.when(pl.col("global_supply") > 0)
                .then(pl.min_horizontal(1.0, pl.col("global_demand") / pl.col("global_supply")))
                .otherwise(0.0)
            ).alias("export_actual"),
            (pl.col("tax_rate") + 0.02).alias("total_tax"),
        )

        unsold_amount = pl.col("export_desired") - pl.col("export_actual")
        new_stock_amount = (
            pl.when(pl.col("is_storable"))
            .then(unsold_amount * (1.0 - pl.col("decay_rate") * fraction))
            .otherwise(0.0)
        )
        production_denominator = pl.max_horizontal(pl.col("domestic_production"), 1.0)
        stock_to_production = new_stock_amount / production_denominator
        market_lf = market_lf.with_columns(
            unsold_amount.alias("unsold_amount"),
            new_stock_amount.alias("new_stock_amount"),
            pl.when(~pl.col("is_storable"))
            .then((unsold_amount / production_denominator) * 0.5 * fraction)
            .when(pl.col("is_storable") & (stock_to_production > 0.5))
            .then(pl.min_horizontal(stock_to_production * 0.05, 0.10) * fraction)
            .otherwise(0.0)
            .alias("production_penalty_pct"),
        )
        market_lf = market_lf.with_columns(
            (pl.col("domestic_production") * (1.0 - pl.col("production_penalty_pct"))).alias("domestic_production"),
            pl.when(pl.col("is_gov_controlled"))
            .then(pl.col("import_actual") * 1.5)
            .otherwise(0.0)
            .alias("gov_import_expense"),
            pl.when(pl.col("is_gov_controlled"))
            .then(pl.col("export_actual") * 1.5)
            .when(pl.col("is_legal"))
            .then((pl.col("import_actual") + pl.col("export_actual")) * pl.col("total_tax"))
            .otherwise(0.0)
            .alias("gov_tax_revenue"),
        )
        market_df = market_lf.collect()
        treaty_effects = state.tables.get("treaty_effects")
        constrained_flows = None
        regional_production = state.tables.get("regional_production")
        if regional_production is not None and not regional_production.is_empty():
            constrained_flows = self._treaty_trade_policy.allocate_with_regional_sources(
                market_df,
                treaty_effects if treaty_effects is not None else pl.DataFrame(),
                regional_production,
                lambda region_id, exporter_id, importer_id: regional_trade_access_allowed(
                    state,
                    region_id,
                    exporter_id,
                    importer_id,
                ),
            )
            market_df = self._apply_constrained_flows(market_df, constrained_flows, fraction)
            countries_df = self._countries_from_constrained_market(state, market_df)
        elif self._treaty_trade_policy.has_constraints(treaty_effects):
            constrained_flows = self._treaty_trade_policy.allocate(market_df, treaty_effects)
            market_df = self._apply_constrained_flows(market_df, constrained_flows, fraction)
            countries_df = self._countries_from_constrained_market(state, market_df)
        else:
            budget_updates = stable_group_sums(
                market_df,
                ("country_id",),
                {
                    "gov_tax_revenue": "trade_income",
                    "gov_import_expense": "trade_expense",
                },
            )
            countries_df = (
                state.get_table("countries")
                .drop(["trade_income", "trade_expense"], strict=False)
                .join(budget_updates, left_on="id", right_on="country_id", how="left")
                .with_columns(pl.col(["trade_income", "trade_expense"]).fill_null(0.0))
            )

        market_df = market_df.sort(["country_id", "game_resource_id"])
        stockpiles = market_df.select([
            "country_id",
            "game_resource_id",
            pl.col("new_stock_amount").alias("stock_amount"),
        ])
        # All downstream projections preserve this canonical order, so sort once
        # instead of materializing a separate sortedness check for each table.
        state.update_table("stockpiles", stockpiles)
        exports_df = market_df.filter(pl.col("export_actual") > 0).select([
            pl.col("country_id").alias("exporter_id"),
            pl.lit("WORLD").alias("importer_id"),
            pl.col("game_resource_id"),
            pl.col("export_actual").alias("trade_value_usd")
        ])
        imports_df = market_df.filter(pl.col("import_actual") > 0).select([
            pl.lit("WORLD").alias("exporter_id"),
            pl.col("country_id").alias("importer_id"),
            pl.col("game_resource_id"),
            pl.col("import_actual").alias("trade_value_usd")
        ])
        if constrained_flows is not None:
            state.update_table(
                "trade_network",
                constrained_flows.sort(
                    ["exporter_id", "importer_id", "game_resource_id"]
                ),
            )
        else:
            state.update_table(
                "trade_network",
                pl.concat([exports_df, imports_df]).sort(
                    ["exporter_id", "importer_id", "game_resource_id"]
                ),
            )

        final_prod_cols = [c for c in market_df.columns if c not in [
            "demand", "stock_amount", "local_supply", "export_desired", "import_desired", "priority", 
            "affordable_import", "global_supply", "global_demand", "imp_ratio", "exp_ratio", 
            "import_actual", "export_actual", "unsold_amount", "new_stock_amount", "stock_to_prod_ratio", 
            "production_penalty_pct", "total_tax", "gov_import_expense", "gov_tax_revenue", "is_storable", "decay_rate", "_economic_trade_modifier"
        ]]
        production = market_df.select(final_prod_cols)
        state.update_table("domestic_production", production)
        state.update_table("countries", ensure_sorted(countries_df, ("id",)))

    def _simulate_market_cycle_fast(self, state: GameState, fraction: float) -> bool:
        """Delegate eligible unconstrained cycles to the composed NumPy simulator."""
        return self._unconstrained_market_simulator.simulate(
            state=state,
            fraction=fraction,
            resource_physics=self.RESOURCE_PHYSICS,
            warning_registry=self._market_column_warning_registry,
        )
    def _apply_treaty_production_bonus(self, state: GameState, production: pl.LazyFrame) -> pl.LazyFrame:
        effects = state.tables.get("treaty_effects")
        if effects is None or effects.is_empty() or "domestic_production" not in production.collect_schema().names():
            return production
        bonuses = stable_group_sums(
            effects.filter(pl.col("effect") == "resource_production_bonus"),
            ("country_id",),
            {"value": "treaty_production_bonus"},
        ).with_columns(pl.col("treaty_production_bonus").clip(0.0, 0.25))
        return (
            production
            .join(bonuses.lazy(), on="country_id", how="left")
            .with_columns((pl.col("domestic_production") * (1.0 + pl.col("treaty_production_bonus").fill_null(0.0))).alias("domestic_production"))
            .drop("treaty_production_bonus")
        )

    def _apply_constrained_flows(self, market: pl.DataFrame, flows: pl.DataFrame, fraction: float) -> pl.DataFrame:
        """Reconcile market balances, stockpiles, and public revenue with bilateral flows."""
        exports = stable_group_sums(
            flows,
            ("exporter_id", "game_resource_id"),
            {"trade_value_usd": "export_actual"},
        ).rename({"exporter_id": "country_id"})
        imports = stable_group_sums(
            flows,
            ("importer_id", "game_resource_id"),
            {"trade_value_usd": "import_actual"},
        ).rename({"importer_id": "country_id"})
        reconciled = (
            market.drop(["import_actual", "export_actual"], strict=False)
            .join(exports, on=["country_id", "game_resource_id"], how="left")
            .join(imports, on=["country_id", "game_resource_id"], how="left")
            .with_columns(pl.col(["import_actual", "export_actual"]).fill_null(0.0))
        )
        base_production = pl.when(1.0 - pl.col("production_penalty_pct") > 0.0).then(
            pl.col("domestic_production") / (1.0 - pl.col("production_penalty_pct"))
        ).otherwise(pl.col("domestic_production"))
        reconciled = reconciled.with_columns(base_production.alias("base_domestic_production"))
        reconciled = reconciled.with_columns(
            (pl.col("export_desired") - pl.col("export_actual")).clip(0.0, None).alias("unsold_amount")
        )
        reconciled = reconciled.with_columns(
            pl.when(pl.col("is_storable"))
            .then(pl.col("unsold_amount") * (1.0 - pl.col("decay_rate") * fraction))
            .otherwise(0.0)
            .alias("new_stock_amount")
        )
        reconciled = reconciled.with_columns(
            pl.when(~pl.col("is_storable"))
            .then((pl.col("unsold_amount") / pl.max_horizontal(pl.col("base_domestic_production"), 1.0)) * 0.5 * fraction)
            .when(pl.col("is_storable") & ((pl.col("new_stock_amount") / pl.max_horizontal(pl.col("base_domestic_production"), 1.0)) > 0.5))
            .then(pl.min_horizontal((pl.col("new_stock_amount") / pl.max_horizontal(pl.col("base_domestic_production"), 1.0)) * 0.05, 0.10) * fraction)
            .otherwise(0.0)
            .alias("production_penalty_pct")
        ).with_columns([
            (pl.col("base_domestic_production") * (1.0 - pl.col("production_penalty_pct"))).alias("domestic_production"),
            pl.when(pl.col("is_gov_controlled")).then(pl.col("import_actual") * 1.5).otherwise(0.0).alias("gov_import_expense"),
            pl.when(pl.col("is_gov_controlled")).then(pl.col("export_actual") * 1.5)
            .when(pl.col("is_legal")).then((pl.col("import_actual") + pl.col("export_actual")) * pl.col("total_tax"))
            .otherwise(0.0)
            .alias("gov_tax_revenue"),
        ])
        return reconciled.drop("base_domestic_production")

    def _countries_from_constrained_market(self, state: GameState, market: pl.DataFrame) -> pl.DataFrame:
        updates = stable_group_sums(
            market,
            ("country_id",),
            {
                "gov_tax_revenue": "trade_income",
                "gov_import_expense": "trade_expense",
            },
        )
        return (
            state.get_table("countries")
            .drop(["trade_income", "trade_expense"], strict=False)
            .join(updates, left_on="id", right_on="country_id", how="left")
            .with_columns(pl.col(["trade_income", "trade_expense"]).fill_null(0.0))
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
