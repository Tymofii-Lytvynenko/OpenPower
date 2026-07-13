"""Executes the bounded cash transfers created by economic-aid treaties."""

from __future__ import annotations

import json
from typing import Any

import polars as pl

from src.engine.interfaces import ISystem
from src.shared.events import EventRealSecond
from src.shared.state import GameState


TRANSFER_SCHEMA = {
    "treaty_id": pl.Utf8,
    "donor_country_id": pl.Utf8,
    "recipient_country_id": pl.Utf8,
    "annual_amount": pl.Float64,
}


class DiplomaticAidSystem(ISystem):
    """Limits aid by both recipient needs and each donor's annual budget."""

    @property
    def id(self) -> str:
        return "base.diplomatic_aid"

    @property
    def dependencies(self) -> list[str]:
        return ["base.diplomacy", "base.budget"]

    def update(self, state: GameState, delta_time: float) -> None:
        heartbeat = next(
            (
                event
                for event in state.events
                if isinstance(event, EventRealSecond) and not event.is_paused and event.game_seconds_passed > 0
            ),
            None,
        )
        if heartbeat is None or "countries" not in state.tables:
            return
        effects = state.tables.get("treaty_effects")
        if effects is None or effects.is_empty():
            state.update_table("diplomatic_aid_transfers", pl.DataFrame(schema=TRANSFER_SCHEMA))
            return

        countries = state.get_table("countries")
        rows = countries.to_dicts()
        by_id = {self._tag(row.get("id")): row for row in rows}
        aid_rows = [
            row for row in effects.to_dicts()
            if str(row.get("effect") or "") == "economic_aid_recipient"
        ]
        transfers = self._plan_transfers(aid_rows, by_id)
        annual_income = {country_id: 0.0 for country_id in by_id}
        annual_expense = {country_id: 0.0 for country_id in by_id}
        for transfer in transfers:
            annual_income[transfer["recipient_country_id"]] += transfer["annual_amount"]
            annual_expense[transfer["donor_country_id"]] += transfer["annual_amount"]

        fraction = heartbeat.game_seconds_passed / (365.25 * 24 * 3600)
        for country_id, row in by_id.items():
            income = annual_income[country_id]
            expense = annual_expense[country_id]
            row["diplomatic_aid_income"] = income
            row["diplomatic_aid_expense"] = expense
            row["money_reserves"] = self._number(row.get("money_reserves")) + (income - expense) * fraction

        state.update_table("countries", pl.DataFrame(rows, schema={**dict(countries.schema),
            "diplomatic_aid_income": pl.Float64,
            "diplomatic_aid_expense": pl.Float64,
        }, strict=False))
        state.update_table("diplomatic_aid_transfers", pl.DataFrame(transfers, schema=TRANSFER_SCHEMA, strict=False) if transfers else pl.DataFrame(schema=TRANSFER_SCHEMA))

    def _plan_transfers(self, aid_rows: list[dict[str, Any]], countries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        remaining_donor_cap = {
            country_id: 0.01 * max(0.0, self._number(row.get("total_annual_expense")))
            for country_id, row in countries.items()
        }
        remaining_recipient_cap = {
            country_id: 0.90 * max(0.0, self._number(row.get("trade_expense")))
            for country_id, row in countries.items()
        }
        transfers: list[dict[str, Any]] = []
        for aid in sorted(aid_rows, key=lambda row: (str(row.get("recipient_country_id") or row.get("country_id") or ""), str(row.get("treaty_id") or ""))):
            recipient = self._tag(aid.get("country_id"))
            if recipient not in countries:
                continue
            donors = self._detail_tags(aid.get("detail"))
            donors = tuple(donor for donor in donors if donor in countries and remaining_donor_cap.get(donor, 0.0) > 0)
            if not donors or remaining_recipient_cap.get(recipient, 0.0) <= 0:
                continue
            request = min(
                max(0.0, self._number(aid.get("value"))) * max(0.0, self._number(countries[recipient].get("trade_expense"))),
                remaining_recipient_cap[recipient],
            )
            if request <= 0:
                continue
            weights = {donor: max(1.0, self._number(countries[donor].get("gdp"))) for donor in donors}
            paid = 0.0
            available_weight = sum(weights.values())
            for donor in donors:
                share = request * weights[donor] / available_weight
                amount = min(share, remaining_donor_cap[donor])
                if amount <= 0:
                    continue
                remaining_donor_cap[donor] -= amount
                paid += amount
                transfers.append({
                    "treaty_id": str(aid.get("treaty_id") or ""),
                    "donor_country_id": donor,
                    "recipient_country_id": recipient,
                    "annual_amount": amount,
                })
            remaining_recipient_cap[recipient] -= paid
        return transfers

    def _detail_tags(self, value: Any) -> tuple[str, ...]:
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return ()
        if not isinstance(parsed, list):
            return ()
        return tuple(sorted({self._tag(item) for item in parsed if self._tag(item)}))

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()

    def _number(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
