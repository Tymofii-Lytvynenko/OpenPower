from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

import polars as pl

from src.shared.actions import GameAction


DECISION_SCHEMA: dict[str, pl.DataType] = {
    "country_id": pl.Utf8,
    "policy_id": pl.Utf8,
    "domain": pl.Utf8,
    "utility": pl.Float64,
    "conflict_key": pl.Utf8,
    "action_kind": pl.Utf8,
    "reason_code": pl.Utf8,
    "quota": pl.UInt32,
}


@dataclass(frozen=True, slots=True)
class AITableContext:
    tables: Mapping[str, pl.DataFrame]
    day_ordinal: int
    total_minutes: int
    date_text: str
    player_tag: str = ""

    def table(self, name: str) -> pl.LazyFrame | None:
        frame = self.tables.get(name)
        return None if frame is None else frame.lazy()


@dataclass(frozen=True, slots=True)
class AIEvaluation:
    actions: tuple[GameAction, ...]
    decisions: pl.DataFrame
    skipped_policies: tuple[str, ...]


@runtime_checkable
class TabularAIPolicy(Protocol):
    id: str
    required_tables: frozenset[str]
    cadence_days: int

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        ...

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        ...


class DeclarativeAIFramework:
    """Compiles independent policy tables into one deterministic decision batch."""

    def __init__(self, *policies: TabularAIPolicy) -> None:
        self._policies: dict[str, TabularAIPolicy] = {}
        self.register(*policies)

    def register(self, *policies: TabularAIPolicy) -> DeclarativeAIFramework:
        for policy in policies:
            if not isinstance(policy, TabularAIPolicy):
                raise TypeError("AI policies must implement the TabularAIPolicy protocol")
            policy_id = str(policy.id).strip()
            if not policy_id:
                raise ValueError("AI policy id cannot be empty")
            if policy_id in self._policies:
                raise ValueError(f"AI policy '{policy_id}' is already registered")
            self._policies[policy_id] = policy
        return self

    @property
    def policy_ids(self) -> tuple[str, ...]:
        return tuple(self._policies)

    def evaluate(self, context: AITableContext) -> AIEvaluation:
        frames: list[pl.LazyFrame] = []
        skipped: list[str] = []
        available_tables = frozenset(context.tables)

        for policy in self._policies.values():
            if not policy.required_tables.issubset(available_tables):
                skipped.append(policy.id)
                continue
            candidates = policy.build_candidates(context)
            if not isinstance(candidates, pl.LazyFrame):
                raise TypeError(f"AI policy '{policy.id}' must return a Polars LazyFrame")
            frames.append(_normalize_candidates(candidates))

        if not frames:
            return AIEvaluation((), empty_decision_frame(), tuple(skipped))

        combined = pl.concat(frames, how="diagonal_relaxed")
        payload_columns = sorted(
            column
            for column in combined.collect_schema().names()
            if column not in DECISION_SCHEMA
        )
        payload_key = (
            pl.struct(payload_columns).struct.json_encode()
            if payload_columns
            else pl.lit("")
        )
        ranked = (
            combined
            .with_columns(payload_key.alias("_payload_key"))
            .filter(
                pl.col("country_id").is_not_null()
                & (pl.col("country_id").str.len_chars() > 0)
                & pl.col("utility").is_finite()
                & (pl.col("utility") > 0.0)
            )
            .sort(
                [
                    "country_id",
                    "domain",
                    "utility",
                    "policy_id",
                    "conflict_key",
                    "action_kind",
                    "reason_code",
                    "quota",
                    "_payload_key",
                ],
                descending=[False, False, True, False, False, False, False, False, False],
                nulls_last=True,
                maintain_order=True,
            )
            .unique(subset=["country_id", "conflict_key"], keep="first", maintain_order=True)
            .with_columns(
                pl.int_range(1, pl.len() + 1)
                .over(["country_id", "domain"])
                .cast(pl.UInt32)
                .alias("rank")
            )
            .filter(pl.col("rank") <= pl.col("quota"))
            .sort(
                ["country_id", "domain", "rank", "policy_id", "conflict_key"],
                maintain_order=True,
            )
            .drop("_payload_key")
        )
        decisions = ranked.collect()

        actions: list[GameAction] = []
        resolvers = self._policies
        for row in decisions.iter_rows(named=True):
            policy = resolvers.get(str(row["policy_id"]))
            if policy is None:
                continue
            action = policy.resolve_action(row)
            if action is not None:
                actions.append(action)

        return AIEvaluation(tuple(actions), decisions, tuple(skipped))


def empty_decision_frame() -> pl.DataFrame:
    return pl.DataFrame(schema={**DECISION_SCHEMA, "rank": pl.UInt32})


def empty_candidates(extra_schema: Mapping[str, pl.DataType] | None = None) -> pl.LazyFrame:
    schema = dict(DECISION_SCHEMA)
    if extra_schema:
        schema.update(extra_schema)
    return pl.DataFrame(schema=schema).lazy()


def scheduled_countries(
    countries: pl.LazyFrame,
    context: AITableContext,
    cadence_days: int,
) -> pl.LazyFrame:
    schema = set(countries.collect_schema().names())
    if "id" not in schema:
        return pl.DataFrame(schema={"country_id": pl.Utf8}).lazy()

    scheduled = countries.with_columns(
        pl.col("id").cast(pl.Utf8).str.to_uppercase().alias("country_id")
    )
    if "is_playable" in schema:
        scheduled = scheduled.filter(pl.col("is_playable").fill_null(True))
    if context.player_tag:
        scheduled = scheduled.filter(pl.col("country_id") != context.player_tag.strip().upper())

    scheduled = scheduled.sort("country_id").with_row_index("_cadence_slot")
    period = max(1, int(cadence_days))
    if period > 1 and context.day_ordinal > 0:
        scheduled = scheduled.filter(
            (pl.col("_cadence_slot") % period) == (int(context.day_ordinal) % period)
        )
    return scheduled.drop("_cadence_slot")


def _normalize_candidates(candidates: pl.LazyFrame) -> pl.LazyFrame:
    schema = candidates.collect_schema()
    expressions: list[pl.Expr] = []
    defaults: dict[str, Any] = {
        "country_id": "",
        "policy_id": "",
        "domain": "",
        "utility": 0.0,
        "conflict_key": "",
        "action_kind": "",
        "reason_code": "",
        "quota": 1,
    }
    for column, dtype in DECISION_SCHEMA.items():
        if column not in schema:
            expressions.append(pl.lit(defaults[column], dtype=dtype).alias(column))
        else:
            expressions.append(pl.col(column).cast(dtype, strict=False).alias(column))
    return candidates.with_columns(expressions).with_columns(
        pl.col("quota").fill_null(1).clip(lower_bound=1),
        pl.col("reason_code").fill_null(""),
    )
