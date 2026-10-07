from __future__ import annotations

import math
from typing import Any, Iterable

import polars as pl


class PeaceDealPolicy:
    """Validates the bounded clause vocabulary shared by peace-deal producers."""

    MAX_CLAUSES = 16
    AI_ACCEPTANCE_PERSONALITY_MODIFIERS = {
        "conciliatory": 0.12,
        "pragmatic": 0.0,
        "hawkish": -0.12,
    }
    CLAUSE_TYPES = frozenset(
        {
            "war_reparations",
            "territory_transfer",
            "treaty_annulment",
            "demilitarization",
        }
    )

    def normalize_clauses(
        self,
        raw_clauses: Any,
    ) -> tuple[list[dict[str, Any]], str]:
        if not isinstance(raw_clauses, list) or len(raw_clauses) > self.MAX_CLAUSES:
            return [], "A peace package must contain a bounded list of clauses."

        normalized: list[dict[str, Any]] = []
        for raw in raw_clauses:
            if not isinstance(raw, dict):
                return [], "Each peace clause must be a structured object."
            clause_type = str(raw.get("type") or "").strip().lower().replace("-", "_")
            if clause_type not in self.CLAUSE_TYPES:
                return [], f"Unsupported peace clause type: {clause_type or 'empty'}."

            clause = self._normalize_clause(clause_type, raw)
            if isinstance(clause, str):
                return [], clause
            normalized.append(clause)
        return normalized, ""

    def validate_clauses(
        self,
        state,
        war: dict[str, Any],
        proposer_country_id: str,
        clauses: Iterable[dict[str, Any]],
    ) -> str:
        side_a = self._country_tags(war.get("side_a"))
        side_b = self._country_tags(war.get("side_b"))
        if proposer_country_id in side_a:
            proposer_side, opposing_side = side_a, side_b
        elif proposer_country_id in side_b:
            proposer_side, opposing_side = side_b, side_a
        else:
            return "The proposer is not a participant in this war."

        countries = state.tables.get("countries")
        country_ids = (
            {str(value).strip().upper() for value in countries.get_column("id").to_list()}
            if countries is not None and "id" in countries.columns
            else set()
        )
        regions = state.tables.get("regions")
        region_rows = (
            {int(row.get("id") or 0): row for row in regions.to_dicts()}
            if regions is not None and "id" in regions.columns
            else {}
        )
        treaties = state.tables.get("countries_treaties")
        treaty_rows = {
            str(row.get("id") or ""): row
            for row in (treaties.to_dicts() if treaties is not None else [])
        }
        seen_targets: set[tuple[str, str]] = set()

        for clause in clauses:
            clause_type = clause["type"]
            if clause_type == "war_reparations":
                payer = clause["payer_country_id"]
                recipient = clause["recipient_country_id"]
                if payer not in country_ids or recipient not in country_ids:
                    return "Reparations require two existing countries."
                if not (
                    (payer in proposer_side and recipient in opposing_side)
                    or (payer in opposing_side and recipient in proposer_side)
                ):
                    return "Reparations must move between the two opposing war sides."
                key = (clause_type, f"{payer}:{recipient}")
            elif clause_type == "territory_transfer":
                region = region_rows.get(clause["region_id"])
                new_owner = clause["new_owner_country_id"]
                current_owner = str((region or {}).get("owner") or "").strip().upper()
                current_controller = str((region or {}).get("controller") or current_owner).strip().upper()
                if region is None or new_owner not in country_ids:
                    return "Territory cessions require an existing region and recipient."
                if current_owner not in proposer_side | opposing_side:
                    return "The territory is not owned by a participant in this war."
                if current_controller not in proposer_side | opposing_side:
                    return "The territory is not controlled by a participant in this war."
                if new_owner not in proposer_side | opposing_side or new_owner == current_owner:
                    return "The new territory owner must be a different war participant."
                key = (clause_type, str(clause["region_id"]))
            elif clause_type == "treaty_annulment":
                treaty = treaty_rows.get(clause["treaty_id"])
                if treaty is None or str(treaty.get("status") or "active").lower() != "active":
                    return "Only an active treaty can be annulled."
                members = self._country_tags(treaty.get("members"))
                if not (members & proposer_side and members & opposing_side):
                    return "The treaty does not bind both opposing war sides."
                key = (clause_type, clause["treaty_id"])
            else:
                country_id = clause["country_id"]
                if country_id not in country_ids or country_id not in proposer_side | opposing_side:
                    return "Demilitarization must name a country participating in the war."
                key = (clause_type, country_id)

            if key in seen_targets:
                return "A peace package cannot apply conflicting duplicate clauses."
            seen_targets.add(key)
        return ""

    def evaluate_ai_acceptance(
        self,
        state,
        war: dict[str, Any],
        responder_country_id: str,
        clauses: Iterable[dict[str, Any]],
    ) -> float:
        """Score a settlement using national costs, battlefield position, and war pressure."""
        responder = self._tag(responder_country_id)
        side_a = self._country_tags(war.get("side_a"))
        side_b = self._country_tags(war.get("side_b"))
        own_side, opposing_side = (side_a, side_b) if responder in side_a else (side_b, side_a)
        countries = state.tables.get("countries")
        rows = [] if countries is None else countries.to_dicts()
        by_id = {self._tag(row.get("id")): row for row in rows}
        own_strength = sum(max(0, int(by_id.get(country, {}).get("military_count") or 0)) for country in own_side)
        enemy_strength = sum(max(0, int(by_id.get(country, {}).get("military_count") or 0)) for country in opposing_side)
        strength_share = max(0.0, min(1.0, own_strength / max(1, own_strength + enemy_strength)))

        exhaustion = 0.0
        exhaustion_table = state.tables.get("war_exhaustion_states")
        if exhaustion_table is not None and not exhaustion_table.is_empty():
            records = exhaustion_table.filter(
                (pl.col("war_id") == str(war.get("id") or ""))
                & (pl.col("country_id").cast(pl.Utf8).str.to_uppercase() == responder)
            )
            if not records.is_empty():
                exhaustion = max(0.0, min(100.0, float(records.item(0, "exhaustion_index") or 0.0))) / 100.0

        utility = 0.48 + exhaustion * 0.28 + (0.5 - strength_share) * 0.28
        personality = str(
            by_id.get(responder, {}).get("diplomatic_ai_archetype") or "pragmatic"
        ).strip().lower()
        utility += self.AI_ACCEPTANCE_PERSONALITY_MODIFIERS.get(personality, 0.0)
        for clause in clauses:
            clause_type = str(clause.get("type") or "")
            if clause_type == "war_reparations":
                amount = max(0.0, self._finite(clause.get("amount"), 0.0))
                country = by_id.get(responder, {})
                gdp = max(1.0, self._finite(country.get("gdp"), 1.0))
                reserves = self._finite(country.get("money_reserves"), 0.0)
                if self._tag(clause.get("payer_country_id")) == responder:
                    burden = amount / gdp
                    utility -= min(0.3, 0.08 + burden * 0.2)
                    if amount > max(0.0, reserves) + max(
                        0.0,
                        self._finite(country.get("total_annual_revenue"), 0.0)
                        - self._finite(country.get("total_annual_expense"), 0.0),
                    ):
                        utility -= 0.12
                elif self._tag(clause.get("recipient_country_id")) == responder:
                    utility += min(0.15, amount / gdp * 0.1)
            elif clause_type == "territory_transfer":
                region_id = int(clause.get("region_id") or 0)
                regions = state.tables.get("regions")
                if regions is not None and "id" in regions.columns:
                    match = regions.filter(pl.col("id") == region_id)
                    current_owner = self._tag(match.item(0, "owner")) if not match.is_empty() else ""
                    if self._tag(clause.get("new_owner_country_id")) == responder:
                        utility += 0.12
                    elif current_owner == responder:
                        utility -= 0.16
            elif clause_type == "demilitarization" and self._tag(clause.get("country_id")) == responder:
                current_strength = max(0, int(by_id.get(responder, {}).get("military_count") or 0))
                cap = max(0, int(clause.get("maximum_strength") or 0))
                utility -= 0.04 + min(0.18, max(0, current_strength - cap) / max(1, current_strength) * 0.18)
            elif clause_type == "treaty_annulment":
                treaties = state.tables.get("countries_treaties")
                if treaties is not None and "id" in treaties.columns:
                    match = treaties.filter(pl.col("id") == str(clause.get("treaty_id") or ""))
                    if not match.is_empty():
                        treaty_type = str(match.item(0, "type") or "").strip().lower()
                        members = self._country_tags(match.item(0, "members"))
                        if responder in members and treaty_type != "alliance":
                            utility += 0.03
                        elif responder in members:
                            utility -= 0.05

        treaties = state.tables.get("countries_treaties")
        if treaties is not None:
            now = max(0, int(state.time.total_minutes))
            owes_alliance = False
            for row in treaties.to_dicts():
                if (
                    str(row.get("status") or "active").lower() != "active"
                    or str(row.get("type") or "").strip().lower() != "alliance"
                ):
                    continue
                expires_at = self._integer(row.get("expires_at_minute"), 0)
                if expires_at > 0 and expires_at <= now:
                    continue
                members = self._country_tags(row.get("members"))
                suspended_members = self._country_tags(row.get("suspended_members"))
                if (
                    responder in members
                    and responder not in suspended_members
                    and bool(members & own_side - {responder})
                ):
                    owes_alliance = True
                    break
            if owes_alliance:
                utility -= 0.08 * (1.0 - exhaustion)

        return max(0.0, min(1.0, utility))

    def _normalize_clause(self, clause_type: str, raw: dict[str, Any]) -> dict[str, Any] | str:
        if clause_type == "war_reparations":
            payer = self._tag(raw.get("payer_country_id"))
            recipient = self._tag(raw.get("recipient_country_id"))
            amount = self._finite(raw.get("amount"), math.nan)
            duration = self._integer(raw.get("duration_months"), 12)
            if not payer or not recipient or payer == recipient:
                return "Reparations must name distinct payer and recipient countries."
            if not math.isfinite(amount) or amount <= 0.0 or duration < 1 or duration > 360:
                return "Reparations require a positive finite amount and a 1–360 month term."
            return {
                "type": clause_type,
                "payer_country_id": payer,
                "recipient_country_id": recipient,
                "amount": amount,
                "duration_months": duration,
            }
        if clause_type == "territory_transfer":
            region_id = self._integer(raw.get("region_id"), 0)
            new_owner = self._tag(raw.get("new_owner_country_id"))
            if region_id <= 0 or not new_owner:
                return "Territory cessions require a positive region id and a new owner."
            return {
                "type": clause_type,
                "region_id": region_id,
                "new_owner_country_id": new_owner,
            }
        if clause_type == "treaty_annulment":
            treaty_id = str(raw.get("treaty_id") or "").strip()
            if not treaty_id:
                return "Treaty annulment requires a treaty id."
            return {"type": clause_type, "treaty_id": treaty_id}
        country_id = self._tag(raw.get("country_id"))
        maximum_strength = self._integer(raw.get("maximum_strength"), -1)
        duration = self._integer(raw.get("duration_days"), 0)
        if not country_id or maximum_strength < 0 or duration < 1 or duration > 3650:
            return "Demilitarization requires a country, non-negative force cap, and 1–3650 days."
        return {
            "type": clause_type,
            "country_id": country_id,
            "maximum_strength": maximum_strength,
            "duration_days": duration,
        }

    @staticmethod
    def _country_tags(value: Any) -> set[str]:
        if isinstance(value, str):
            values = value.split(",")
        elif isinstance(value, (list, tuple, set)):
            values = value
        else:
            values = ()
        return {str(item).strip().upper() for item in values if str(item).strip()}

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _finite(value: Any, fallback: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return fallback
        return number if math.isfinite(number) else fallback

    @classmethod
    def _integer(cls, value: Any, fallback: int) -> int:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return fallback
        if not math.isfinite(number) or int(number) != number:
            return fallback
        return int(number)
