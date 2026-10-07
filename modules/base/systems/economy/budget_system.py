from typing import NamedTuple

import numpy as np
import polars as pl
from src.shared.economy_meta import RESOURCE_MAPPING
from modules.base.systems.world.random_event_effects import aggregate_active_effects
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE
from src.shared.state import GameState
from src.shared.numeric import (
    stable_group_sums,
    stable_nonnegative_row_totals,
)
from src.shared.actions import ActionUpdateBudget
from src.shared.events import EventRealSecond
from modules.base.systems.politics.political_effect_policy import aggregate_political_effects


_REQUIRED_COUNTRY_DEFAULTS = {
    "gdp": 0.0, "human_dev": 0.5, "personal_income_tax_rate": 0.2,
    "budget_imf_ratio": 0.0, "trade_income": 0.0, "trade_expense": 0.0,
    "budget_edu_ratio": 0.5, "budget_health_ratio": 0.5, "budget_social_ratio": 0.5, "budget_env_ratio": 0.5,
    "budget_infra_ratio": 0.5, "budget_telecom_ratio": 0.5, "budget_gov_ratio": 0.5,
    "budget_propaganda_ratio": 0.5, "budget_tourism_promo_ratio": 0.5,
    "budget_research_ratio": 0.5, "budget_imf_ratio": 0.0,
    "security_upkeep": 0.0, "diplomacy_upkeep": 0.0, "treaty_maintenance": 0.0,
    "diplomatic_aid_expense": 0.0,
    "corruption_index": 0.1, "military_count": 0, "money_reserves": 0.0,
    "interest_rate": 0.05,
    "economic_policy_modifier": 1.0,
    "annual_debt_service": 0.0,
}
_DENSE_RESOURCE_ORDER = tuple(sorted(RESOURCE_MAPPING))
_FAST_NUMERIC_TYPES = frozenset(
    {
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
)


class _DenseDemandLayoutCache(NamedTuple):
    country_ids: pl.Series
    ledger_country_ids: pl.Series
    ledger_resource_ids: pl.Series


class BudgetSystem(ISystem):
    """
    Handles national budget calculations including revenues, dynamic sector expenses, 
    debt interest, and tax fairness.
    
    This system treats tourism income as a specific 20% levy on foreign currency 
    inflows (exports of tourism services), providing additional revenue beyond 
    standard internal taxation.
    """

    access = SystemAccess(
        reads=frozenset({'countries', 'resource_ledger', 'units', 'unit_designs', 'random_event_effects', 'political_effects'}),
        writes=frozenset({'countries'}),
        handles=frozenset({ActionUpdateBudget}),
        phase=SystemPhase.BUDGET,
    )

    runtime_state_contract = {
        "_missing_columns": SYSTEM_STATE_CACHE,
        "_dense_demand_layout_cache": SYSTEM_STATE_CACHE,
    }

    # Constants for revenue and interest
    PERSONAL_INCOME_TAX_CONSTANT = 3.0 
    DEBT_INTEREST_RATE = 0.05
    # The percentage of foreign tourism spending that goes directly to the state budget
    TOURISM_FOREIGN_LEVY_RATE = 0.20 
    
    # Base budget multiplier for social/infra demand
    K_BUDGET = 0.15
    
    # Sector expense ratios (multipliers for total demand)
    M_SECTOR = {
        "budget_health_ratio": 0.25,
        "budget_edu_ratio": 0.23,
        "budget_social_ratio": 0.15,
        "budget_gov_ratio": 0.14,
        "budget_env_ratio": 0.10,
        "budget_research_ratio": 0.09,
        "budget_infra_ratio": 0.07,
        "budget_telecom_ratio": 0.04,
        "budget_imf_ratio": 0.04,
        "budget_propaganda_ratio": 0.03,
        "budget_tourism_promo_ratio": 0.01
    }

    def __init__(self):
        self._missing_columns = set()
        self._dense_demand_layout_cache: _DenseDemandLayoutCache | None = None

    @property
    def id(self) -> str:
        return "base.budget"

    @property
    def dependencies(self) -> list[str]:
        # Depends on Trade to ensure 'trade_network' (exports) is calculated first
        return ["base.time", "base.economy", "base.trade"]

    def update(self, state: GameState, delta_time: float) -> None:
        # 1. Handle Incoming Actions (e.g., player changing budget sliders)
        for action in state.current_actions:
            if isinstance(action, ActionUpdateBudget):
                self._handle_update_budget(state, action)

        # 2. Process Periodic Simulation via Real Second Heartbeat
        real_sec_events = [e for e in state.events if isinstance(e, EventRealSecond)]
        
        for event in real_sec_events:
            if event.is_paused or event.game_seconds_passed <= 0:
                continue
            
            # Convert game time passed into a fraction of a year for annual rates
            fraction_of_year = event.game_seconds_passed / (365.25 * 24 * 3600)
            self._process_budget(state, fraction_of_year)

    def _calculate_tourism_revenue(self, state: GameState) -> pl.LazyFrame:
        """
        Calculates revenue from foreign tourists based on tourism service exports.
        Logic: 20% of all tourism services 'sold' to the world (foreign currency).
        """
        if "trade_network" not in state.tables:
            return pl.DataFrame(schema={"id": pl.Utf8, "tourism_income": pl.Float64}).lazy()

        tourism_exports = state.get_table("trade_network").filter(
            (pl.col("game_resource_id") == "tourism_services")
            & (pl.col("exporter_id") != "WORLD")
        )
        if tourism_exports.is_empty():
            return pl.DataFrame(schema={"id": pl.Utf8, "tourism_income": pl.Float64}).lazy()

        revenue = stable_group_sums(
            tourism_exports,
            ("exporter_id",),
            {"trade_value_usd": "tourism_income"},
        )
        return revenue.with_columns(
            (pl.col("tourism_income") * self.TOURISM_FOREIGN_LEVY_RATE).alias("tourism_income")
        ).rename({"exporter_id": "id"}).lazy()

    def _process_budget(self, state: GameState, fraction: float) -> None:
        if "countries" not in state.tables:
            return

        if self._try_process_budget_fast(state, fraction):
            return

        # Prepare Total Demand per country from resource ledger
        if "resource_ledger" in state.tables:
            demand_lf = stable_group_sums(
                state.get_table("resource_ledger"),
                ("country_id",),
                {"consumption_usd": "total_demand"},
            ).lazy()
        else:
            demand_lf = pl.DataFrame(schema={"country_id": pl.Utf8, "total_demand": pl.Float64}).lazy()

        # Get Dynamic Tourism Revenue
        tourism_rev_lf = self._calculate_tourism_revenue(state)

        # Start building the main processing LazyFrame
        lf = state.get_table("countries").lazy()
        lf = lf.drop(["total_demand", "tourism_income"], strict=False) # Clean up to avoid join collisions

        budget_pressure = aggregate_active_effects(
            state.tables.get("random_event_effects"),
            int(state.time.total_minutes),
            categories={"budget_pressure"},
            subject_type="country",
        )
        if budget_pressure:
            pressure_frame = pl.DataFrame(
                {
                    "_event_country_id": [subject_id for (_, subject_id, _) in budget_pressure],
                    "_event_budget_pressure": [magnitude for magnitude in budget_pressure.values()],
                }
            )
            lf = lf.join(pressure_frame.lazy(), left_on="id", right_on="_event_country_id", how="left").with_columns(
                pl.col("_event_budget_pressure").fill_null(0.0).clip(-0.5, 1.0)
            )
        else:
            lf = lf.with_columns(pl.lit(0.0).alias("_event_budget_pressure"))

        political_tax_deltas = aggregate_political_effects(
            state.tables.get("political_effects"),
            int(state.time.total_minutes),
            domain="tax",
            effect="personal_income_tax_rate_delta",
        )
        if political_tax_deltas:
            tax_delta_frame = pl.DataFrame(
                {
                    "_political_tax_country_id": list(political_tax_deltas),
                    "_political_tax_delta": list(political_tax_deltas.values()),
                }
            )
            lf = lf.join(
                tax_delta_frame.lazy(),
                left_on="id",
                right_on="_political_tax_country_id",
                how="left",
            ).with_columns(pl.col("_political_tax_delta").fill_null(0.0).clip(-1.0, 1.0))
        else:
            lf = lf.with_columns(pl.lit(0.0).alias("_political_tax_delta"))
        
        # Joins
        lf = lf.join(demand_lf, left_on="id", right_on="country_id", how="left").with_columns(
            pl.col("total_demand").fill_null(0.0)
        )
        lf = lf.join(tourism_rev_lf, on="id", how="left").with_columns(
            pl.col("tourism_income").fill_null(0.0)
        )

        # Ensure required columns for calculations exist with defaults
        required_cols = _REQUIRED_COUNTRY_DEFAULTS.copy()
        required_cols["interest_rate"] = self.DEBT_INTEREST_RATE

        existing_cols = set(state.get_table("countries").columns)
        for col, default_val in required_cols.items():
            if col not in existing_cols:
                if col not in self._missing_columns:
                    print(f"[{self.id}] Column '{col}' not found. Defaulting to {default_val}.")
                    self._missing_columns.add(col)
                lf = lf.with_columns(pl.lit(default_val).alias(col))

        lf = lf.with_columns(
            (
                pl.col("personal_income_tax_rate").fill_null(0.2)
                + pl.col("_political_tax_delta")
            )
            .clip(0.0, 1.0)
            .alias("_effective_income_tax_rate")
        )

        # --- REVENUE CALCULATION ---
        
        # 1. Personal Income Tax
        lf = lf.with_columns(
            ((pl.col("gdp") * pl.col("human_dev") * pl.col("_effective_income_tax_rate"))
             / self.PERSONAL_INCOME_TAX_CONSTANT).alias("revenue_tax")
        )

        # 2. Total Revenue (includes our dynamic tourism_income)
        lf = lf.with_columns(
            (
                (
                    pl.col("revenue_tax")
                    + pl.col("trade_income")
                    + pl.col("tourism_income")
                    + pl.col("budget_imf_ratio")
                ) * pl.col("economic_policy_modifier").fill_null(1.0).clip(0.0, 1.0)
            ).alias("total_annual_revenue")
        )

        # --- EXPENSE CALCULATION ---

        # 1. Social and Infrastructure Sectors
        expense_components = [
            (pl.col("total_demand") * self.K_BUDGET * multiplier * pl.col(col_name))
            for col_name, multiplier in self.M_SECTOR.items()
        ]
        lf = lf.with_columns(pl.sum_horizontal(expense_components).alias("expense_social_and_infra"))
        lf = lf.with_columns(
            pl.max_horizontal(
                0.0,
                pl.col("total_demand")
                * self.K_BUDGET
                * pl.col("_event_budget_pressure"),
            ).alias("expense_random_event_pressure")
        )

        # 2. Governance / Corruption loss
        lf = lf.with_columns((pl.col("gdp") * pl.col("budget_gov_ratio") * pl.col("corruption_index")).alias("expense_corruption"))

        # 3. Military Upkeep
        BASE_UNIT_COST = 500_000.0
        readiness_factors = self._readiness_upkeep_factors(state)
        readiness_frame = self._readiness_upkeep_by_country(state, readiness_factors)
        if readiness_frame is not None:
            lf = lf.join(readiness_frame.lazy(), on="id", how="left").with_columns(
                pl.col("_readiness_upkeep_factor").fill_null(1.0),
                pl.col("_design_maintenance").fill_null(0.0),
            )
        else:
            lf = lf.with_columns(
                pl.lit(1.0).alias("_readiness_upkeep_factor"),
                pl.lit(0.0).alias("_design_maintenance"),
            )
        lf = lf.with_columns(
            (
                pl.col("military_count") * BASE_UNIT_COST * pl.col("human_dev")
                * pl.col("_readiness_upkeep_factor") + pl.col("_design_maintenance")
            ).alias("expense_military_upkeep")
        )

        # 4. Debt Interest
        lf = lf.with_columns(
            pl.when(pl.col("money_reserves") < 0)
            .then(
                pl.col("money_reserves").abs()
                * pl.col("interest_rate").fill_null(self.DEBT_INTEREST_RATE).clip(0.0, 0.5)
            )
            .otherwise(0.0)
            .alias("expense_debt_interest")
        )

        # 5. Total Annual Expense
        lf = lf.with_columns(
            (
                pl.col("expense_social_and_infra") +
                pl.col("expense_random_event_pressure") +
                pl.col("expense_corruption") +
                pl.col("expense_military_upkeep") +
                pl.col("expense_debt_interest") +
                pl.col("annual_debt_service").fill_null(0.0).clip(lower_bound=0.0) +
                pl.col("security_upkeep") +
                pl.col("diplomacy_upkeep") +
                pl.col("treaty_maintenance") +
                pl.col("diplomatic_aid_expense") +
                pl.col("trade_expense")
            ).alias("total_annual_expense")
        )

        # --- TAX FAIRNESS FACTOR ---
        
        lf = lf.with_columns(
            ((pl.col("budget_edu_ratio") + pl.col("budget_env_ratio") + 
              pl.col("budget_health_ratio") + pl.col("budget_telecom_ratio") + 
              pl.col("budget_infra_ratio") + pl.col("budget_social_ratio")) / 6.0).alias("_avg_social_spending")
        )

        lf = lf.with_columns(pl.max_horizontal(0.0, (2.0 * pl.col("_effective_income_tax_rate")) - 0.2).alias("_expected_spending"))

        lf = lf.with_columns(
            pl.when(pl.col("_expected_spending") == 0.0).then(1.0)
            .otherwise(pl.min_horizontal(1.0, pl.col("_avg_social_spending") / pl.col("_expected_spending")))
            .alias("tax_fairness_factor")
        )

        # --- FINAL STATE UPDATE ---
        
        lf = lf.with_columns(
            (
                pl.col("money_reserves")
                + (
                    pl.col("total_annual_revenue")
                    - pl.col("total_annual_expense")
                    + pl.col("annual_debt_service").fill_null(0.0).clip(lower_bound=0.0)
                ) * fraction
            )
            .alias("money_reserves")
        )

        # Cleanup internal calculation columns
        lf = lf.drop(["_avg_social_spending", "_expected_spending", "_effective_income_tax_rate", "_political_tax_delta", "_readiness_upkeep_factor", "_design_maintenance", "_event_budget_pressure", "expense_random_event_pressure"])

        state.update_table("countries", lf.collect().sort("id"))

    def _try_process_budget_fast(self, state: GameState, fraction: float) -> bool:
        """Use aligned numeric vectors for ordinary worlds without active modifiers."""
        countries = state.tables.get("countries")
        ledger = state.tables.get("resource_ledger")
        if (
            countries is None
            or ledger is None
            or not {"id"}.issubset(countries.columns)
            or not {"country_id", "game_resource_id", "consumption_usd"}.issubset(ledger.columns)
        ):
            return False

        for table_name in (
            "random_event_effects",
            "political_effects",
            "units",
            "unit_designs",
        ):
            table = state.tables.get(table_name)
            if table is not None and not table.is_empty():
                return False

        trade_network = state.tables.get("trade_network")
        if trade_network is not None and not {
            "exporter_id", "game_resource_id", "trade_value_usd"
        }.issubset(trade_network.columns):
            return False

        total_demand = self._dense_total_demand(countries, ledger)
        if total_demand is None:
            return False

        country_ids = countries.get_column("id")
        if countries.schema["id"] != pl.String or not country_ids.is_sorted():
            return False
        country_count = countries.height
        country_id_values = country_ids.to_list()

        def values(column: str, *, fill_null: float | None = None) -> np.ndarray | None:
            if column not in countries.columns:
                return np.full(country_count, _REQUIRED_COUNTRY_DEFAULTS[column], dtype=np.float64)
            series = countries.get_column(column)
            if series.dtype not in _FAST_NUMERIC_TYPES:
                return None
            if series.null_count():
                if fill_null is None:
                    return None
                series = series.fill_null(fill_null)
            return series.cast(pl.Float64, strict=False).to_numpy()

        numeric_values: dict[str, np.ndarray] = {}
        null_defaults = {
            "personal_income_tax_rate": 0.2,
            "economic_policy_modifier": 1.0,
            "interest_rate": self.DEBT_INTEREST_RATE,
            "annual_debt_service": 0.0,
        }
        for column in _REQUIRED_COUNTRY_DEFAULTS:
            column_values = values(column, fill_null=null_defaults.get(column))
            if column_values is None:
                return False
            numeric_values[column] = column_values

        demand_values = total_demand.get_column("total_demand").to_numpy()
        if trade_network is None or trade_network.is_empty():
            tourism_by_country: dict[str, float] = {}
        else:
            tourism_revenue = self._calculate_tourism_revenue(state).collect()
            tourism_by_country = dict(
                zip(
                    tourism_revenue.get_column("id").to_list(),
                    tourism_revenue.get_column("tourism_income").to_list(),
                    strict=True,
                )
            )
        tourism_income = np.fromiter(
            (tourism_by_country.get(country_id, 0.0) for country_id in country_id_values),
            dtype=np.float64,
            count=country_count,
        )

        effective_tax = np.clip(
            numeric_values["personal_income_tax_rate"], 0.0, 1.0
        )
        revenue_tax = (
            numeric_values["gdp"]
            * numeric_values["human_dev"]
            * effective_tax
            / self.PERSONAL_INCOME_TAX_CONSTANT
        )
        total_revenue = (
            revenue_tax
            + numeric_values["trade_income"]
            + tourism_income
            + numeric_values["budget_imf_ratio"]
        ) * np.clip(numeric_values["economic_policy_modifier"], 0.0, 1.0)

        social_expense = np.zeros(country_count, dtype=np.float64)
        for column, multiplier in self.M_SECTOR.items():
            social_expense += (
                demand_values
                * self.K_BUDGET
                * multiplier
                * numeric_values[column]
            )
        corruption_expense = (
            numeric_values["gdp"]
            * numeric_values["budget_gov_ratio"]
            * numeric_values["corruption_index"]
        )
        military_upkeep = (
            numeric_values["military_count"]
            * 500_000.0
            * numeric_values["human_dev"]
        )
        debt_interest = np.where(
            numeric_values["money_reserves"] < 0.0,
            np.abs(numeric_values["money_reserves"])
            * np.clip(numeric_values["interest_rate"], 0.0, 0.5),
            0.0,
        )
        total_expense = (
            social_expense
            + corruption_expense
            + military_upkeep
            + debt_interest
            + np.maximum(numeric_values["annual_debt_service"], 0.0)
            + numeric_values["security_upkeep"]
            + numeric_values["diplomacy_upkeep"]
            + numeric_values["treaty_maintenance"]
            + numeric_values["diplomatic_aid_expense"]
            + numeric_values["trade_expense"]
        )
        average_social_spending = sum(
            numeric_values[column]
            for column in (
                "budget_edu_ratio",
                "budget_env_ratio",
                "budget_health_ratio",
                "budget_telecom_ratio",
                "budget_infra_ratio",
                "budget_social_ratio",
            )
        ) / 6.0
        expected_spending = np.maximum(0.0, (2.0 * effective_tax) - 0.2)
        fairness = np.ones(country_count, dtype=np.float64)
        np.divide(
            average_social_spending,
            expected_spending,
            out=fairness,
            where=expected_spending > 0.0,
        )
        fairness = np.minimum(1.0, fairness)
        annual_debt_service = np.maximum(numeric_values["annual_debt_service"], 0.0)
        reserves = numeric_values["money_reserves"] + (
            total_revenue - total_expense + annual_debt_service
        ) * fraction

        additions = [
            pl.Series("total_demand", demand_values),
            pl.Series("tourism_income", tourism_income),
        ]
        existing_columns = set(countries.columns)
        for column, default in _REQUIRED_COUNTRY_DEFAULTS.items():
            if column in existing_columns:
                continue
            if column not in self._missing_columns:
                print(f"[{self.id}] Column '{column}' not found. Defaulting to {default}.")
                self._missing_columns.add(column)
            additions.append(pl.Series(column, [default] * country_count))
        additions.extend(
            [
                pl.Series("revenue_tax", revenue_tax),
                pl.Series("total_annual_revenue", total_revenue),
                pl.Series("expense_social_and_infra", social_expense),
                pl.Series("expense_corruption", corruption_expense),
                pl.Series("expense_military_upkeep", military_upkeep),
                pl.Series("expense_debt_interest", debt_interest),
                pl.Series("total_annual_expense", total_expense),
                pl.Series("tax_fairness_factor", fairness),
                pl.Series("money_reserves", reserves),
            ]
        )

        updated = countries.with_columns(additions).drop(
            [
                "_avg_social_spending",
                "_expected_spending",
                "_effective_income_tax_rate",
                "_political_tax_delta",
                "_readiness_upkeep_factor",
                "_design_maintenance",
                "_event_budget_pressure",
                "expense_random_event_pressure",
            ],
            strict=False,
        )
        state.update_table("countries", updated)
        return True

    def _dense_total_demand(
        self,
        countries: pl.DataFrame,
        ledger: pl.DataFrame,
    ) -> pl.DataFrame | None:
        """Aggregate a complete canonical country/resource grid without hashing rows."""
        country_ids = countries.get_column("id")
        country_count = countries.height
        resource_count = len(_DENSE_RESOURCE_ORDER)
        if ledger.height != country_count * resource_count:
            return None

        ledger_country_ids = ledger.get_column("country_id")
        ledger_resource_ids = ledger.get_column("game_resource_id")
        cache = self._dense_demand_layout_cache
        cache_hit = (
            cache is not None
            and cache.country_ids.equals(country_ids)
            and cache.ledger_country_ids.equals(ledger_country_ids)
            and cache.ledger_resource_ids.equals(ledger_resource_ids)
        )
        if not cache_hit:
            if (
                countries.schema.get("id") != pl.String
                or not country_ids.is_sorted()
                or len(set(country_ids.to_list())) != country_count
            ):
                return None
            expected_keys = countries.select(pl.col("id").alias("country_id")).join(
                pl.DataFrame({"game_resource_id": _DENSE_RESOURCE_ORDER}),
                how="cross",
            )
            if (
                not expected_keys.get_column("country_id").equals(ledger_country_ids)
                or not expected_keys.get_column("game_resource_id").equals(ledger_resource_ids)
            ):
                return None
            self._dense_demand_layout_cache = _DenseDemandLayoutCache(
                country_ids,
                ledger_country_ids,
                ledger_resource_ids,
            )

        demand_values = (
            ledger.get_column("consumption_usd")
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
            .to_numpy()
            .reshape(country_count, resource_count)
        )
        totals = stable_nonnegative_row_totals(demand_values)
        return pl.DataFrame(
            {
                "id": country_ids,
                "total_demand": totals,
            }
        )

    def _readiness_upkeep_factors(self, state: GameState) -> dict[str, float]:
        configured = state.globals.get("military_readiness_upkeep_factors", {})
        if not isinstance(configured, dict):
            return {}
        factors: dict[str, float] = {}
        for status in ("parked", "ready", "fortified"):
            if status not in configured:
                continue
            try:
                value = float(configured[status])
            except (TypeError, ValueError, OverflowError):
                continue
            if value == value and abs(value) != float("inf"):
                factors[status] = max(0.0, min(2.0, value))
        return factors

    def _readiness_upkeep_by_country(self, state: GameState, factors: dict[str, float]) -> pl.DataFrame | None:
        units = state.tables.get("units")
        if units is None or "owner" not in units.columns or "strength" not in units.columns:
            return None
        unit_lf = units.lazy().with_columns(
            pl.col("owner").cast(pl.Utf8).alias("id"),
            pl.col("strength").cast(pl.Float64).fill_null(0.0).clip(lower_bound=0.0).alias("_maintenance_strength"),
        )
        if "readiness_status" in units.columns and factors:
            status = pl.col("readiness_status").cast(pl.Utf8).str.to_lowercase()
            factor_expr = pl.lit(1.0)
            for readiness, factor in factors.items():
                factor_expr = pl.when(status == readiness).then(pl.lit(factor)).otherwise(factor_expr)
            unit_lf = unit_lf.with_columns(factor_expr.alias("_readiness_factor"))
        else:
            unit_lf = unit_lf.with_columns(pl.lit(1.0).alias("_readiness_factor"))

        maintenance_lf = None
        designs = state.tables.get("unit_designs")
        if designs is not None and "id" in designs.columns and "maintenance_cost" in designs.columns and "design_id" in units.columns:
            design_lf = designs.lazy().select(
                pl.col("id").cast(pl.Utf8).alias("_maintenance_design_id"),
                pl.col("maintenance_cost").cast(pl.Float64).fill_null(0.0).clip(0.0, 1_000_000_000_000.0).alias("_maintenance_per_unit"),
            )
            maintenance_lf = (
                unit_lf.join(design_lf, left_on="design_id", right_on="_maintenance_design_id", how="left")
                .group_by("id")
                .agg((pl.col("_maintenance_strength") * pl.col("_maintenance_per_unit").fill_null(0.0)).sum().alias("_design_maintenance"))
            )
        readiness_lf = unit_lf.group_by("id").agg(
            pl.col("_maintenance_strength").sum().alias("_total_unit_strength"),
            (pl.col("_maintenance_strength") * pl.col("_readiness_factor")).sum().alias("_weighted_unit_strength"),
        )
        if maintenance_lf is not None:
            readiness_lf = readiness_lf.join(maintenance_lf, on="id", how="left")
        else:
            readiness_lf = readiness_lf.with_columns(pl.lit(0.0).alias("_design_maintenance"))
        return readiness_lf.with_columns(
            pl.when(pl.col("_total_unit_strength") > 0.0)
            .then(pl.col("_weighted_unit_strength") / pl.col("_total_unit_strength"))
            .otherwise(1.0)
            .alias("_readiness_upkeep_factor")
        ).select("id", "_readiness_upkeep_factor", "_design_maintenance").collect()

    def _handle_update_budget(self, state: GameState, action: ActionUpdateBudget) -> None:
        if "countries" not in state.tables:
            return
        
        df = state.get_table("countries")
        updates = []
        for col, val in action.allocations.items():
            if col in self.M_SECTOR or col == "personal_income_tax_rate":
                clamped_val = max(0.0, min(1.0, float(val)))
                updates.append(
                    pl.when(pl.col("id") == action.country_tag)
                    .then(pl.lit(clamped_val))
                    .otherwise(pl.col(col))
                    .alias(col)
                )
        
        if updates:
            state.update_table("countries", df.with_columns(updates))
