import polars as pl

from modules.base.systems.world.ai_strategic import (
    STRATEGIC_AI_SCHEMA_DEFAULTS,
    StrategicDiplomacySnapshotBuilder,
    build_ai_alliance_action,
    build_ai_peace_action,
    build_ai_war_action,
    evaluate_alliance_opportunities,
    evaluate_peace_pressure,
    evaluate_war_opportunities,
)
from src.core.ai_framework import DeclarativeAIFramework
from src.engine.interfaces import ISystem
from src.shared.actions import ActionBuildUnit, ActionUpdateBudget
from src.shared.state import GameState

PLANNING_HORIZON_YEARS = 5.0
UNIT_BUILD_COST = 1_000_000.0
UNIT_ANNUAL_UPKEEP_BASE = 500_000.0
GDP_PROTECTED_PER_INFANTRY = 0.002
MILITARY_DECAY_FACTOR = 0.85
RECRUITMENT_SHARE = 0.001
UNIT_COUNT_DAMPING = 0.25
MIN_RECRUITMENT_BATCH = 1
MAX_RECRUITMENT_BATCH = 250


# =========================================================================
# Pure Functional Scorers (Data-Driven Policy Definitions)
# =========================================================================

def audit_financial_survival(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Evaluates existential economic threat levels across all actors concurrently.
    Uses financial runway tracking instead of soft arbitrary thresholds.
    """
    return lf.with_columns(
        annual_net_income=pl.col("total_annual_revenue") - pl.col("total_annual_expense")
    ).with_columns(
        months_to_bankruptcy=pl.when(pl.col("annual_net_income") < 0)
        .then((pl.col("money_reserves") / pl.col("annual_net_income").abs()) * 12)
        .otherwise(999.0)
    ).with_columns(
        utility_survival_taxes=pl.when(pl.col("months_to_bankruptcy") < 12.0)
        .then((1.0 - (pl.col("months_to_bankruptcy") / 12.0)).clip(0.0, 1.0))
        .otherwise(0.0)
    )


def summarize_unit_snapshot(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Summarizes the active unit table into country-level military signals.

    The AI needs to reason about unit stacks, not raw manpower rows, because
    the military model stores soldiers inside named units. Using the unit row
    count keeps the marginal ROI curve numerically stable for real countries.
    """
    schema = set(lf.collect_schema().names())
    required = {"owner", "strength"}
    if not required.issubset(schema):
        return pl.DataFrame(
            schema={
                "id": pl.Utf8,
                "active_military_strength": pl.Int64,
                "active_unit_count": pl.Int64,
            }
        ).lazy()

    return (
        lf.group_by("owner")
        .agg(
            pl.col("strength").sum().cast(pl.Int64).alias("active_military_strength"),
            pl.count().cast(pl.Int64).alias("active_unit_count"),
        )
        .rename({"owner": "id"})
    )


def calculate_military_roi(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Computes the ROI of recruiting another infantry batch from the current unit model.

    The old version used total manpower as the decay exponent, which underflowed
    almost immediately for real countries. We now base diminishing returns on
    the number of unit stacks, because that is what the tactical layer actually
    exposes to the player.
    """
    return lf.with_columns(
        current_military_strength=pl.max_horizontal(pl.col("military_count"), pl.col("active_military_strength")),
        reinforcement_gap=pl.max_horizontal(0, pl.col("military_count") - pl.col("active_military_strength")),
    ).with_columns(
        planned_recruitment=pl.when(pl.col("reinforcement_gap") > 0)
        .then(pl.col("reinforcement_gap").clip(MIN_RECRUITMENT_BATCH, MAX_RECRUITMENT_BATCH))
        .otherwise(
            (
                pl.col("current_military_strength")
                * RECRUITMENT_SHARE
                / (1.0 + (pl.col("active_unit_count") * UNIT_COUNT_DAMPING))
            )
            .round(0)
            .clip(MIN_RECRUITMENT_BATCH, MAX_RECRUITMENT_BATCH)
        )
        .cast(pl.Int64)
    ).with_columns(
        unit_5y_cost=((
            UNIT_BUILD_COST
            + (UNIT_ANNUAL_UPKEEP_BASE * pl.col("human_dev") * PLANNING_HORIZON_YEARS)
        ) * pl.col("planned_recruitment")),
    ).with_columns(
        unit_5y_benefit=(
            pl.col("gdp")
            * GDP_PROTECTED_PER_INFANTRY
            * pl.lit(MILITARY_DECAY_FACTOR).pow(pl.col("active_unit_count"))
            * pl.col("trait_threat_perception")
            * pl.col("planned_recruitment").cast(pl.Float64).sqrt()
        )
    ).with_columns(
        military_roi=(pl.col("unit_5y_benefit") - pl.col("unit_5y_cost")) / pl.col("unit_5y_cost")
    ).with_columns(
        utility_build_infantry=pl.when(
            (pl.col("military_roi") > 0.0)
            & (pl.col("money_reserves") > pl.col("unit_5y_cost"))
            & (pl.col("annual_net_income") > 0.0)
        )
        .then(pl.col("military_roi").clip(0.0, 1.0))
        .otherwise(0.0)
    )


# =========================================================================
# ECS System Layer Integration
# =========================================================================

class AISystem(ISystem):
    """
    System boundary exposing the data-driven framework to the simulation scheduler loop.
    Acts as a pluggable driver node in the engine graph.
    """

    def __init__(self):
        self._missing_columns = set()
        self._framework = DeclarativeAIFramework()
        self._diplomacy_snapshot_builder = StrategicDiplomacySnapshotBuilder()
        self._bootstrap_framework()

    @property
    def id(self) -> str:
        return "base.ai"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time"]

    def _bootstrap_framework(self) -> None:
        """Wires up reusable policy scorers and row-to-action resolvers once on init."""
        self._framework.register_scorer(audit_financial_survival)
        self._framework.register_scorer(calculate_military_roi)
        self._framework.register_scorer(evaluate_alliance_opportunities)
        self._framework.register_scorer(evaluate_war_opportunities)
        self._framework.register_scorer(evaluate_peace_pressure)

        self._framework.register_action_resolver(
            "utility_survival_taxes",
            lambda row: ActionUpdateBudget(
                "ai_system",
                row["id"],
                {"personal_income_tax_rate": min(0.50, row["personal_income_tax_rate"] + 0.02)},
            ),
        )

        self._framework.register_action_resolver(
            "utility_build_infantry",
            lambda row: ActionBuildUnit("ai_system", row["id"], "infantry", int(row["planned_recruitment"])),
        )

        self._framework.register_action_resolver("utility_seek_alliance", build_ai_alliance_action)
        self._framework.register_action_resolver("utility_declare_war", build_ai_war_action)
        self._framework.register_action_resolver("utility_offer_peace", build_ai_peace_action)

    def _apply_schema_fallbacks(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """Guarantees structural data integrity across hot-loaded mod configurations."""
        schema = lf.collect_schema().names()
        defaults = {
            "total_annual_revenue": 0.0,
            "total_annual_expense": 0.0,
            "money_reserves": 0.0,
            "gdp": 10_000_000.0,
            "human_dev": 0.5,
            "personal_income_tax_rate": 0.20,
            "trait_threat_perception": 1.0,
            "military_count": 0,
        }

        for col, default_val in defaults.items():
            if col not in schema:
                if col not in self._missing_columns:
                    print(f"[{self.id}] Schema anomaly recovery: Defaulting '{col}' to {default_val}")
                    self._missing_columns.add(col)
                lf = lf.with_columns(pl.lit(default_val).alias(col))

        return lf

    def _ensure_derived_defaults(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """
        Fills optional snapshot/scorer columns without treating them as source schema anomalies.

        These fields are expected to disappear when the unit or diplomacy tables are absent,
        so the AI should recreate them quietly instead of printing recovery noise every tick.
        """
        schema = set(lf.collect_schema().names())
        defaults = {
            "active_military_strength": 0,
            "active_unit_count": 0,
            "current_military_strength": 0,
            "reinforcement_gap": 0,
            "planned_recruitment": 0,
            **STRATEGIC_AI_SCHEMA_DEFAULTS,
        }
        fill_expressions: list[pl.Expr] = []

        for column, default_value in defaults.items():
            if column not in schema:
                lf = lf.with_columns(pl.lit(default_value).alias(column))
                schema.add(column)
                continue

            if isinstance(default_value, int):
                fill_expressions.append(pl.col(column).fill_null(int(default_value)).alias(column))
            elif isinstance(default_value, float):
                fill_expressions.append(pl.col(column).fill_null(float(default_value)).alias(column))
            else:
                fill_expressions.append(pl.col(column).fill_null(str(default_value)).alias(column))

        if not fill_expressions:
            return lf
        return lf.with_columns(fill_expressions)

    def update(self, state: GameState, delta_time: float) -> None:
        from src.shared.events import EventNewDay

        has_new_day = any(isinstance(event, EventNewDay) for event in state.events)
        if not has_new_day or state.time.is_paused or "countries" not in state.tables:
            return

        countries_lf = state.get_table("countries").lazy()
        countries_lf = self._apply_schema_fallbacks(countries_lf)
        countries_lf = self._attach_unit_snapshot(countries_lf, state)
        countries_lf = self._attach_diplomacy_snapshot(countries_lf, state)
        countries_lf = self._ensure_derived_defaults(countries_lf)

        actions = self._framework.evaluate_and_act(countries_lf)
        state.current_actions.extend(actions)

    def _attach_unit_snapshot(self, countries_lf: pl.LazyFrame, state: GameState) -> pl.LazyFrame:
        units = state.tables.get("units")
        if units is None:
            return countries_lf

        countries_lf = countries_lf.drop(["active_military_strength", "active_unit_count"], strict=False)
        unit_snapshot = summarize_unit_snapshot(units.lazy())
        return (
            countries_lf.join(unit_snapshot, on="id", how="left")
            .with_columns(
                pl.col("active_military_strength").fill_null(0),
                pl.col("active_unit_count").fill_null(0),
            )
        )

    def _attach_diplomacy_snapshot(self, countries_lf: pl.LazyFrame, state: GameState) -> pl.LazyFrame:
        countries = state.get_table("countries")
        snapshot = self._diplomacy_snapshot_builder.build(
            countries=countries,
            relations=state.tables.get("countries_relations"),
            treaties=state.tables.get("countries_treaties"),
            wars=state.tables.get("countries_wars"),
            strength_by_country=self._country_strength_map(countries, state.tables.get("units")),
        )
        if snapshot.is_empty():
            return countries_lf

        strategic_columns = [column for column in snapshot.columns if column != "id"]
        countries_lf = countries_lf.drop(strategic_columns, strict=False)
        return countries_lf.join(snapshot.lazy(), on="id", how="left")

    def _country_strength_map(self, countries: pl.DataFrame, units: pl.DataFrame | None) -> dict[str, int]:
        strength_by_country: dict[str, int] = {}
        if not countries.is_empty() and {"id", "military_count"}.issubset(set(countries.columns)):
            for row in countries.select(["id", "military_count"]).iter_rows(named=True):
                strength_by_country[str(row["id"])] = max(0, int(row.get("military_count") or 0))

        if units is None or units.is_empty() or not {"owner", "strength"}.issubset(set(units.columns)):
            return strength_by_country

        for row in units.select(["owner", "strength"]).iter_rows(named=True):
            owner = str(row.get("owner") or "").strip().upper()
            if not owner:
                continue
            unit_strength = max(0, int(row.get("strength") or 0))
            strength_by_country[owner] = strength_by_country.get(owner, 0) + unit_strength

        return strength_by_country


