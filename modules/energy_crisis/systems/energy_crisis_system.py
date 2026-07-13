from __future__ import annotations

import math

import polars as pl

from modules.energy_crisis.actions import ActionSetEnergyPolicy
from modules.energy_crisis.events import EventEnergyPolicyChanged
from src.shared.events import EventNewDay
from src.shared.state import GameState
from src.shared.system_interfaces import SystemAccess, SystemPhase


POLICY_EFFECTS = {
    "market": {"recovery": 0.2, "depletion": 1.0, "drag": 1.0},
    "conservation": {"recovery": 0.8, "depletion": 0.75, "drag": 0.8},
    "rationing": {"recovery": 1.2, "depletion": 0.55, "drag": 1.1},
    "subsidies": {"recovery": 0.9, "depletion": 0.8, "drag": 0.9},
}


class EnergyCrisisSystem:
    access = SystemAccess(
        reads=frozenset({"countries", "energy_crises"}),
        writes=frozenset({"countries", "energy_crises"}),
        handles=frozenset({ActionSetEnergyPolicy}),
        phase=SystemPhase.POST_PROCESS,
    )

    @property
    def id(self) -> str:
        return "energy_crisis.simulation"

    @property
    def dependencies(self) -> list[str]:
        return ["base.budget"]

    def update(self, state: GameState, delta_time: float) -> None:
        _ = delta_time
        status = state.tables.get("energy_crises")
        if status is None:
            return

        changed = False
        country_tags = self._country_tags(state)
        for action in state.current_actions:
            if not isinstance(action, ActionSetEnergyPolicy):
                continue
            tag = action.country_tag.strip().upper()
            if tag not in country_tags:
                raise ValueError(f"Unknown energy-policy country '{tag}'.")
            status = self._apply_policy(status, tag, action)
            state.events.append(
                EventEnergyPolicyChanged(
                    country_tag=tag,
                    policy=action.policy,
                    response_level=float(action.response_level),
                )
            )
            changed = True

        if any(isinstance(event, EventNewDay) for event in state.events):
            status = self._advance_day(status)
            changed = True

        if changed:
            state.update_table("energy_crises", status)
        self._update_country_metrics(state, status)

    def _apply_policy(
        self,
        status: pl.DataFrame,
        country_tag: str,
        action: ActionSetEnergyPolicy,
    ) -> pl.DataFrame:
        policy = action.policy.strip().lower()
        if policy not in POLICY_EFFECTS:
            supported = ", ".join(sorted(POLICY_EFFECTS))
            raise ValueError(
                f"Unknown energy policy '{action.policy}'. Supported: {supported}."
            )

        response = float(action.response_level)
        if not math.isfinite(response) or not 0.0 <= response <= 1.0:
            raise ValueError("Energy response_level must be finite and between 0 and 1.")

        existing = status.filter(pl.col("country_id") == country_tag)
        if existing.is_empty():
            row = {
                "country_id": country_tag,
                "policy": policy,
                "reserve_days": 90.0,
                "import_dependency": 0.5,
                "shock_intensity": 0.0,
                "response_level": response,
                "stress_index": 0.0,
                "economic_drag": 0.0,
            }
            return pl.concat(
                [status, pl.DataFrame([row])],
                how="diagonal_relaxed",
            )

        return status.with_columns(
            pl.when(pl.col("country_id") == country_tag)
            .then(pl.lit(policy))
            .otherwise(pl.col("policy"))
            .alias("policy"),
            pl.when(pl.col("country_id") == country_tag)
            .then(pl.lit(response))
            .otherwise(pl.col("response_level"))
            .alias("response_level"),
        )

    def _advance_day(self, status: pl.DataFrame) -> pl.DataFrame:
        rows: list[dict[str, object]] = []
        for row in status.iter_rows(named=True):
            policy = str(row.get("policy") or "market").lower()
            effects = POLICY_EFFECTS.get(policy, POLICY_EFFECTS["market"])
            reserve_days = self._ratio(row.get("reserve_days"), 90.0, maximum=365.0)
            dependency = self._ratio(row.get("import_dependency"), 0.5)
            shock = self._ratio(row.get("shock_intensity"), 0.0)
            response = self._ratio(row.get("response_level"), 0.0)

            stress = self._clamp(
                shock + dependency * (1.0 - reserve_days / 180.0) - response * 0.45
            )
            reserve_days = max(
                0.0,
                min(
                    365.0,
                    reserve_days
                    + response * effects["recovery"]
                    - stress * (1.4 + dependency) * effects["depletion"],
                ),
            )
            economic_drag = min(0.25, stress * 0.08 * effects["drag"])

            updated = dict(row)
            updated.update(
                {
                    "policy": policy,
                    "reserve_days": reserve_days,
                    "shock_intensity": max(0.0, shock * 0.995),
                    "stress_index": stress,
                    "economic_drag": economic_drag,
                }
            )
            rows.append(updated)

        return pl.DataFrame(rows, schema=status.schema, strict=False) if rows else status

    def _update_country_metrics(
        self,
        state: GameState,
        status: pl.DataFrame,
    ) -> None:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return

        metric_columns = [
            column
            for column in ("energy_security_index", "energy_economic_drag")
            if column in countries.columns
        ]
        base = countries.drop(metric_columns)
        metrics = status.select(
            pl.col("country_id").alias("id"),
            (1.0 - pl.col("stress_index")).clip(0.0, 1.0).alias(
                "energy_security_index"
            ),
            pl.col("economic_drag").alias("energy_economic_drag"),
        )
        updated = (
            base.join(metrics, on="id", how="left")
            .with_columns(
                pl.col("energy_security_index").fill_null(1.0),
                pl.col("energy_economic_drag").fill_null(0.0),
            )
        )
        if not updated.equals(countries):
            state.update_table("countries", updated)

    @staticmethod
    def _country_tags(state: GameState) -> set[str]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return set()
        return {str(value).upper() for value in countries["id"].to_list()}

    @classmethod
    def _ratio(
        cls,
        value: object,
        default: float,
        *,
        maximum: float = 1.0,
    ) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(number):
            return default
        return max(0.0, min(maximum, number))

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))
