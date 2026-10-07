from functools import lru_cache
from typing import NamedTuple

import numpy as np
import polars as pl
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE, SYSTEM_STATE_HELPER
from src.shared.state import GameState
from src.shared.numeric import stable_group_sums, stable_sum
from src.shared.frames import ensure_sorted
from src.shared.events import EventRealSecond
from modules.base.systems.economy.treaty_trade_policy import TreatyTradePolicy
from modules.base.systems.economy.input_validation import validate_numeric_columns
from modules.base.systems.world.recognition_policy import regional_trade_access_allowed


@lru_cache(maxsize=4)
def _resource_market_metadata(
    physics_entries: tuple[tuple[str, bool, float], ...],
) -> tuple[dict[str, int], np.ndarray, np.ndarray]:
    resource_ids = tuple(resource_id for resource_id, _, _ in physics_entries)
    indices_by_id = {resource_id: index for index, resource_id in enumerate(resource_ids)}
    decay_rates = np.fromiter(
        (decay_rate for _, _, decay_rate in physics_entries),
        dtype=np.float64,
        count=len(physics_entries),
    )
    storable = np.fromiter(
        (is_storable for _, is_storable, _ in physics_entries),
        dtype=np.bool_,
        count=len(physics_entries),
    )
    return (
        indices_by_id,
        decay_rates,
        storable,
    )


class _MarketIndexCache(NamedTuple):
    country_ids: pl.Series
    production_country_ids: pl.Series
    production_resource_ids: pl.Series
    physics_entries: tuple[tuple[str, bool, float], ...]
    country_indices: np.ndarray
    resource_indices: np.ndarray
    keys_are_sorted: bool
    country_ids_precede_world: bool


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

    def __init__(self):
        self._missing_columns = set()
        self._market_index_cache: _MarketIndexCache | None = None
        self._treaty_trade_policy = TreatyTradePolicy()

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
        validate_numeric_columns(
            state.get_table("domestic_production"),
            "domestic_production",
            ("domestic_production", "tax_rate"),
            nonnegative=("domestic_production", "tax_rate"),
        )
        resource_ledger = state.tables.get("resource_ledger")
        if resource_ledger is not None:
            validate_numeric_columns(
                resource_ledger,
                "resource_ledger",
                ("consumption_usd",),
                nonnegative=("consumption_usd",),
            )
        stockpiles = state.tables.get("stockpiles")
        if stockpiles is not None:
            validate_numeric_columns(
                stockpiles,
                "stockpiles",
                ("stock_amount",),
                nonnegative=("stock_amount",),
            )
        validate_numeric_columns(
            state.get_table("countries"),
            "countries",
            ("economic_trade_modifier",),
        )

        countries = state.get_table("countries")
        countries_lf = countries.lazy()
        country_columns = set(countries.columns)
        trade_modifier = (
            pl.col("economic_trade_modifier").cast(pl.Float64, strict=False).fill_null(1.0).clip(0.5, 1.0)
            if "economic_trade_modifier" in country_columns
            else pl.lit(1.0)
        )
        trade_modifiers = countries_lf.select(
            pl.col("id").alias("country_id"),
            trade_modifier.alias("_economic_trade_modifier"),
        )
        production = state.get_table("domestic_production")
        prod_lf = production.lazy()
        prod_lf = self._apply_treaty_production_bonus(state, prod_lf)
        
        if "resource_ledger" in state.tables:
            demand_lf = state.get_table("resource_ledger").lazy().select(
                pl.col("country_id"), pl.col("game_resource_id"), pl.col("consumption_usd").alias("demand")
            )
        else:
            demand_lf = prod_lf.select(["country_id", "game_resource_id"]).with_columns(pl.lit(0.0).alias("demand"))

        if "stockpiles" in state.tables:
            stock_lf = state.get_table("stockpiles").lazy()
        else:
            stock_lf = prod_lf.select(["country_id", "game_resource_id"]).with_columns(pl.lit(0.0).alias("stock_amount"))

        market_lf = prod_lf.join(demand_lf, on=["country_id", "game_resource_id"], how="left").with_columns(
            pl.col("demand").fill_null(0.0)
        )
        market_lf = market_lf.join(trade_modifiers, on="country_id", how="left").with_columns(
            pl.col("_economic_trade_modifier").fill_null(1.0)
        )
        market_lf = market_lf.join(stock_lf, on=["country_id", "game_resource_id"], how="left").with_columns(
            pl.col("stock_amount").fill_null(0.0)
        )

        # Ensure Meta columns exist
        market_cols = production.columns
        if "is_gov_controlled" not in market_cols:
            if "is_gov_controlled" not in self._missing_columns:
                print(f"[{self.id}] Column 'is_gov_controlled' not found in 'domestic_production'. Defaulting to False.")
                self._missing_columns.add("is_gov_controlled")
            market_lf = market_lf.with_columns(pl.lit(False).alias("is_gov_controlled"))
        if "is_legal" not in market_cols:
            if "is_legal" not in self._missing_columns:
                print(f"[{self.id}] Column 'is_legal' not found in 'domestic_production'. Defaulting to True.")
                self._missing_columns.add("is_legal")
            market_lf = market_lf.with_columns(pl.lit(True).alias("is_legal"))
        if "tax_rate" not in market_cols:
            if "tax_rate" not in self._missing_columns:
                print(f"[{self.id}] Column 'tax_rate' not found in 'domestic_production'. Defaulting to 0.05.")
                self._missing_columns.add("tax_rate")
            market_lf = market_lf.with_columns(pl.lit(0.05).alias("tax_rate"))

        # Add Physical Properties
        market_lf = market_lf.join(_resource_physics_table().lazy(), on="game_resource_id", how="left").with_columns([
            pl.col("is_storable").fill_null(True),
            pl.col("decay_rate").fill_null(0.10)
        ])

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
        """Use aligned NumPy columns when the market has no bilateral constraints."""
        production = state.tables.get("domestic_production")
        countries = state.tables.get("countries")
        ledger = state.tables.get("resource_ledger")
        regional = state.tables.get("regional_production")
        treaty_effects = state.tables.get("treaty_effects")
        if (
            production is None
            or countries is None
            or ledger is None
            or production.is_empty()
            or (regional is not None and not regional.is_empty())
            or (treaty_effects is not None and not treaty_effects.is_empty())
            or not {"country_id", "game_resource_id", "domestic_production"}.issubset(production.columns)
            or not {"country_id", "game_resource_id", "consumption_usd"}.issubset(ledger.columns)
            or not {"id"}.issubset(countries.columns)
        ):
            return False

        key_columns = ("country_id", "game_resource_id")
        production_country_ids = production.get_column("country_id")
        production_resource_ids = production.get_column("game_resource_id")
        country_id_series = countries.get_column("id")
        if (
            countries.schema["id"] != pl.String
            or production.schema["country_id"] != pl.String
            or production.schema["game_resource_id"] != pl.String
        ):
            return False

        physics_entries = tuple(
            (
                resource_id,
                bool(values["is_storable"]),
                float(values["decay_rate"]),
            )
            for resource_id, values in self.RESOURCE_PHYSICS.items()
        )
        cached_indices = self._market_index_cache
        cache_hit = (
            cached_indices is not None
            and cached_indices.country_ids.equals(country_id_series)
            and cached_indices.production_country_ids.equals(production_country_ids)
            and cached_indices.production_resource_ids.equals(production_resource_ids)
            and cached_indices.physics_entries == physics_entries
        )

        # A cached row mapping is valid only for the exact immutable key columns and
        # country order from which it was built; ledger/stockpile alignment is still
        # checked on every call because those tables have independent lifecycles.
        if (
            not production_country_ids.equals(ledger.get_column("country_id"))
            or not production_resource_ids.equals(ledger.get_column("game_resource_id"))
        ):
            return False

        stockpiles = state.tables.get("stockpiles")
        if stockpiles is not None:
            if not {"country_id", "game_resource_id", "stock_amount"}.issubset(stockpiles.columns):
                return False
            if (
                not production_country_ids.equals(stockpiles.get_column("country_id"))
                or not production_resource_ids.equals(stockpiles.get_column("game_resource_id"))
            ):
                return False

        row_count = production.height
        if not cache_hit and (
            production.select(pl.struct(key_columns).is_duplicated().any()).item()
            or country_id_series.null_count() > 0
            or production_country_ids.null_count() > 0
            or production_resource_ids.null_count() > 0
        ):
            return False
        keys_are_sorted = (
            cached_indices.keys_are_sorted
            if cache_hit
            else production.select(pl.struct(key_columns)).to_series().is_sorted()
        )
        country_ids_precede_world = (
            cached_indices.country_ids_precede_world
            if cache_hit
            else all(country_id < "WORLD" for country_id in country_id_series.to_list())
        )

        supported_numeric_types = {
            pl.Float32,
            pl.Float64,
            pl.Int8,
            pl.Int16,
            pl.Int32,
            pl.Int64,
            pl.UInt8,
            pl.UInt16,
            pl.UInt32,
            pl.UInt64,
        }
        numeric_columns = (
            (production, "domestic_production"),
            (production, "tax_rate"),
            (ledger, "consumption_usd"),
            (countries, "economic_trade_modifier"),
            (stockpiles, "stock_amount"),
        )
        if any(
            frame is not None
            and column in frame.columns
            and frame.schema[column] not in supported_numeric_types
            for frame, column in numeric_columns
        ):
            return False
        (
            resource_indices_by_id,
            decay_rates_by_resource,
            storable_by_resource,
        ) = _resource_market_metadata(physics_entries)
        if cache_hit:
            country_indices = cached_indices.country_indices
            resource_indices = cached_indices.resource_indices
        else:
            country_values = production_country_ids.to_numpy()
            resource_values = production_resource_ids.to_numpy()
            country_ids = country_id_series.to_list()
            country_index_by_id = {
                str(country_id): index for index, country_id in enumerate(country_ids)
            }
            if len(country_index_by_id) != len(country_ids):
                return False
            # Build Python hash mappings once per stable key layout, not once per tick.
            country_indices = np.fromiter(
                (country_index_by_id.get(country_id, -1) for country_id in country_values),
                dtype=np.int32,
                count=row_count,
            )
            resource_indices = np.fromiter(
                (resource_indices_by_id.get(resource_id, -1) for resource_id in resource_values),
                dtype=np.int32,
                count=row_count,
            )
        if (country_indices < 0).any() or (resource_indices < 0).any():
            return False

        production_column = production.get_column("domestic_production")
        for table, column in (
            (production, "domestic_production"),
            (production, "tax_rate"),
            (production, "is_gov_controlled"),
            (production, "is_legal"),
        ):
            if column in table.columns and table.get_column(column).null_count():
                return False
        production_values = production_column.cast(pl.Float64, strict=False).to_numpy()
        if not np.isfinite(production_values).all():
            return False

        def numeric_values(frame: pl.DataFrame, column: str, default: float) -> np.ndarray:
            if column not in frame.columns:
                return np.full(row_count, default, dtype=np.float64)
            return (
                frame.get_column(column)
                .cast(pl.Float64, strict=False)
                .fill_null(default)
                .to_numpy()
            )

        demand = numeric_values(ledger, "consumption_usd", 0.0)
        stock = (
            numeric_values(stockpiles, "stock_amount", 0.0)
            if stockpiles is not None
            else np.zeros(row_count, dtype=np.float64)
        )
        country_columns = set(countries.columns)
        trade_modifier_values = (
            countries.get_column("economic_trade_modifier")
            .cast(pl.Float64, strict=False)
            .fill_null(1.0)
            .to_numpy()
            if "economic_trade_modifier" in country_columns
            else np.ones(countries.height, dtype=np.float64)
        )
        if not np.isfinite(trade_modifier_values).all():
            raise ValueError(
                "countries.economic_trade_modifier must contain finite values."
            )
        trade_modifiers_by_country = np.clip(trade_modifier_values, 0.5, 1.0)
        trade_modifiers = trade_modifiers_by_country[country_indices]
        if "is_gov_controlled" in production.columns:
            government_controlled = (
                production.get_column("is_gov_controlled")
                .cast(pl.Boolean, strict=False)
                .fill_null(False)
                .to_numpy()
            )
        else:
            if "is_gov_controlled" not in self._missing_columns:
                print(f"[{self.id}] Column 'is_gov_controlled' not found in 'domestic_production'. Defaulting to False.")
                self._missing_columns.add("is_gov_controlled")
            government_controlled = np.zeros(row_count, dtype=np.bool_)
        if "is_legal" in production.columns:
            legal = (
                production.get_column("is_legal")
                .cast(pl.Boolean, strict=False)
                .fill_null(False)
                .to_numpy()
            )
        else:
            if "is_legal" not in self._missing_columns:
                print(f"[{self.id}] Column 'is_legal' not found in 'domestic_production'. Defaulting to True.")
                self._missing_columns.add("is_legal")
            legal = np.ones(row_count, dtype=np.bool_)
        tax_rates = numeric_values(production, "tax_rate", 0.05)
        if "tax_rate" not in production.columns and "tax_rate" not in self._missing_columns:
            print(f"[{self.id}] Column 'tax_rate' not found in 'domestic_production'. Defaulting to 0.05.")
            self._missing_columns.add("tax_rate")

        for table_name, column_name, values, require_nonnegative in (
            ("domestic_production", "domestic_production", production_values, True),
            ("resource_ledger", "consumption_usd", demand, True),
            ("stockpiles", "stock_amount", stock, True),
            ("domestic_production", "tax_rate", tax_rates, True),
            ("countries", "economic_trade_modifier", trade_modifiers_by_country, False),
        ):
            if not np.isfinite(values).all() or (
                require_nonnegative and (values < 0.0).any()
            ):
                raise ValueError(
                    f"{table_name}.{column_name} must contain finite"
                    f"{' and non-negative' if require_nonnegative else ''} values."
                )

        local_supply = production_values + stock
        export_desired = np.maximum(local_supply - demand, 0.0)
        import_desired = np.maximum(demand - local_supply, 0.0)
        affordable_import = import_desired * trade_modifiers
        global_supply = np.bincount(
            resource_indices,
            weights=export_desired,
            minlength=len(decay_rates_by_resource),
        )
        global_demand = np.bincount(
            resource_indices,
            weights=affordable_import,
            minlength=len(decay_rates_by_resource),
        )
        resource_supply = global_supply[resource_indices]
        resource_demand = global_demand[resource_indices]
        import_ratio = np.divide(
            resource_supply,
            resource_demand,
            out=np.zeros(row_count, dtype=np.float64),
            where=resource_demand > 0.0,
        )
        export_ratio = np.divide(
            resource_demand,
            resource_supply,
            out=np.zeros(row_count, dtype=np.float64),
            where=resource_supply > 0.0,
        )
        import_actual = affordable_import * np.minimum(1.0, import_ratio)
        export_actual = export_desired * np.minimum(1.0, export_ratio)
        unsold_amount = export_desired - export_actual
        storable = storable_by_resource[resource_indices]
        decay_rates = decay_rates_by_resource[resource_indices]
        new_stock = np.where(storable, unsold_amount * (1.0 - decay_rates * fraction), 0.0)
        production_denominator = np.maximum(production_values, 1.0)
        stock_to_production = new_stock / production_denominator
        production_penalty = np.where(
            ~storable,
            (unsold_amount / production_denominator) * 0.5 * fraction,
            np.where(
                stock_to_production > 0.5,
                np.minimum(stock_to_production * 0.05, 0.10) * fraction,
                0.0,
            ),
        )
        updated_production = production_values * (1.0 - production_penalty)
        total_tax = tax_rates + 0.02
        government_import_expense = np.where(government_controlled, import_actual * 1.5, 0.0)
        government_tax_revenue = np.where(
            government_controlled,
            export_actual * 1.5,
            np.where(legal, (import_actual + export_actual) * total_tax, 0.0),
        )
        trade_income = np.bincount(
            country_indices,
            weights=government_tax_revenue,
            minlength=countries.height,
        )
        trade_expense = np.bincount(
            country_indices,
            weights=government_import_expense,
            minlength=countries.height,
        )

        production_updates = [
            pl.Series("domestic_production", updated_production),
            pl.Series("stock_amount", new_stock),
        ]
        if "is_gov_controlled" not in production.columns:
            production_updates.append(
                pl.Series("is_gov_controlled", government_controlled)
            )
        if "is_legal" not in production.columns:
            production_updates.append(pl.Series("is_legal", legal))
        if "tax_rate" not in production.columns:
            production_updates.append(pl.Series("tax_rate", tax_rates))
        market_output = production.with_columns(production_updates)
        cached_country_indices = country_indices
        cached_resource_indices = resource_indices
        if not keys_are_sorted:
            # The output contract sorts market rows; carry the aligned index vectors
            # through that same permutation so the next tick can reuse the cache.
            sort_order = np.lexsort(
                (production_resource_ids.to_numpy(), production_country_ids.to_numpy())
            )
            cached_country_indices = country_indices[sort_order]
            cached_resource_indices = resource_indices[sort_order]
            market_output = ensure_sorted(market_output, key_columns)
        if not cache_hit:
            self._market_index_cache = _MarketIndexCache(
                country_id_series,
                market_output.get_column("country_id"),
                market_output.get_column("game_resource_id"),
                physics_entries,
                cached_country_indices,
                cached_resource_indices,
                True,
                country_ids_precede_world,
            )
        state.update_table(
            "stockpiles",
            market_output.select(
                "country_id",
                "game_resource_id",
                "stock_amount",
            ),
        )

        flow_schema = {
            "exporter_id": pl.Utf8,
            "importer_id": pl.Utf8,
            "game_resource_id": pl.Utf8,
            "trade_value_usd": pl.Float64,
        }
        positive_exports = np.flatnonzero(export_actual > 0.0)
        positive_imports = np.flatnonzero(import_actual > 0.0)
        export_rows = pl.DataFrame(
            {
                "exporter_id": production_country_ids.gather(positive_exports),
                "importer_id": ["WORLD"] * len(positive_exports),
                "game_resource_id": production_resource_ids.gather(positive_exports),
                "trade_value_usd": export_actual[positive_exports],
            },
            schema=flow_schema,
        )
        import_rows = pl.DataFrame(
            {
                "exporter_id": ["WORLD"] * len(positive_imports),
                "importer_id": production_country_ids.gather(positive_imports),
                "game_resource_id": production_resource_ids.gather(positive_imports),
                "trade_value_usd": import_actual[positive_imports],
            },
            schema=flow_schema,
        )
        trade_network = pl.concat([export_rows, import_rows])
        if not (keys_are_sorted and country_ids_precede_world):
            trade_network = trade_network.sort(
                ["exporter_id", "importer_id", "game_resource_id"]
            )
        state.update_table("trade_network", trade_network)
        state.update_table(
            "domestic_production",
            market_output.drop("stock_amount"),
        )
        updated_countries = countries.with_columns(
            pl.Series("trade_income", trade_income),
            pl.Series("trade_expense", trade_expense),
        )
        if not country_id_series.is_sorted():
            updated_countries = ensure_sorted(updated_countries, ("id",))
        state.update_table("countries", updated_countries)
        return True

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
