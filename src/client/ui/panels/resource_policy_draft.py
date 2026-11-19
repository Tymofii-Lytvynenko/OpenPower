"""Client-owned resource drafts and snapshot acknowledgements."""
import math
from dataclasses import dataclass, field

import polars as pl


@dataclass(frozen=True)
class ResourceMarketValues:
    global_tax_modifier: float = 0.02
    desired_trade_usd: float = 0.0
    meet_consumption: bool = True


@dataclass
class ResourcePolicyDraft:
    baseline_management: int
    baseline_status: int
    baseline_tax: int
    management: int
    status: int
    tax: int
    baseline_market: ResourceMarketValues = field(default_factory=ResourceMarketValues)
    market_values: ResourceMarketValues = field(default_factory=ResourceMarketValues)

    @property
    def values(self) -> tuple[int, int, int]:
        return self.management, self.status, self.tax

    @property
    def baseline(self) -> tuple[int, int, int]:
        return self.baseline_management, self.baseline_status, self.baseline_tax

    @property
    def is_dirty(self) -> bool:
        return self.values != self.baseline or self.market_values != self.baseline_market

    @property
    def resource_changed(self) -> bool:
        return (self.values != self.baseline
                or self.market_values.desired_trade_usd != self.baseline_market.desired_trade_usd
                or self.market_values.meet_consumption != self.baseline_market.meet_consumption)

    def rebase(self, values, market_values=None) -> None:
        self.baseline_management, self.baseline_status, self.baseline_tax = values
        self.management, self.status, self.tax = values
        if market_values is not None:
            self.baseline_market = self.market_values = market_values


@dataclass(frozen=True)
class PendingResourcePolicy:
    values: tuple[int, int, int]
    player_id: str
    result_cursor: int
    market_values: ResourceMarketValues | None = None
    changes_global_tax: bool = False

    def matches(self, values, market_values) -> bool:
        expected = self.market_values
        return values == self.values and (expected is None or (
            expected.desired_trade_usd == market_values.desired_trade_usd
            and expected.meet_consumption == market_values.meet_consumption
            and (not self.changes_global_tax or expected.global_tax_modifier == market_values.global_tax_modifier)))


def read_market_values(state, country: str, resource: str) -> ResourceMarketValues:
    modifier, desired, automatic = 0.02, 0.0, True
    countries = state.tables.get("countries")
    if countries is not None and {"id", "global_resource_tax_modifier"}.issubset(countries.columns):
        rows = countries.filter(pl.col("id").cast(pl.Utf8).str.strip_chars().str.to_uppercase() == country)
        if rows.height == 1 and rows["global_resource_tax_modifier"][0] is not None:
            modifier = float(rows["global_resource_tax_modifier"][0])
    row = _resource_row(state, country, resource)
    desired = float(row.get("desired_trade_usd") or 0.0)
    automatic = True if row.get("meet_consumption") is None else bool(row["meet_consumption"])
    if not math.isfinite(modifier) or not 0.0 <= modifier <= 1.0:
        raise ValueError("Global resource tax must be a finite ratio from 0 to 1.")
    if not math.isfinite(desired) or abs(desired) > 1e15:
        raise ValueError("Resource trade target must be finite and within ±1,000 trillion USD.")
    return ResourceMarketValues(modifier, desired, automatic)


def read_resource_tax_rate(state, key, fallback: float) -> float:
    row = _resource_row(state, *key)
    value = row.get("tax_rate")
    rate = fallback if value is None else float(value)
    if not math.isfinite(rate) or not 0.0 <= rate <= 1.0:
        raise ValueError("Resource tax must be a finite ratio from 0 to 1.")
    return rate


def _resource_row(state, country, resource) -> dict:
    production = state.tables.get("domestic_production")
    if production is None or not {"country_id", "game_resource_id"}.issubset(production.columns):
        return {}
    rows = production.filter(
        (pl.col("country_id").cast(pl.Utf8).str.strip_chars().str.to_uppercase() == country)
        & (pl.col("game_resource_id").cast(pl.Utf8).str.strip_chars().str.to_lowercase() == resource))
    return rows.row(0, named=True) if rows.height == 1 else {}
