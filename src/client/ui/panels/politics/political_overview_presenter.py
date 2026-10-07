from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

import polars as pl

from src.client.ui.panels.shared.panel_data import safe_int, safe_text

MINUTES_PER_DAY = 24 * 60


@dataclass(frozen=True, slots=True)
class PoliticalPartyView:
    party_id: str
    display_name: str
    support_pct: float | None
    organization_pct: float | None
    eligible: bool | None
    is_ruling: bool


@dataclass(frozen=True, slots=True)
class PoliticalLawView:
    law_id: str
    group_name: str
    title: str
    status: str
    value: str


@dataclass(frozen=True, slots=True)
class PoliticalLawTransitionView:
    law_id: str
    target_value: str
    effective_at_minute: int
    status: str


@dataclass(frozen=True, slots=True)
class PoliticalCauseView:
    game_minute: int
    event_type: str
    reason: str
    result: str


@dataclass(frozen=True, slots=True)
class PoliticalElectionOverrideOptionView:
    override_type: str
    minimum_duration_days: int
    maximum_duration_days: int
    default_duration_days: int
    cost: float | None
    approval_delta: float
    stability_delta: float
    available: bool
    unavailable_reason: str


@dataclass(frozen=True, slots=True)
class PoliticalElectionRecordView:
    status: str
    scheduled_at_minute: int
    resolved_at_minute: int
    winner_party_id: str
    turnout_pct: float | None
    override_type: str
    reason: str


@dataclass(frozen=True, slots=True)
class PoliticalOverviewViewModel:
    country_id: str
    government_form: str
    ruling_party: str
    election_eligible: bool | None
    next_election_at_minute: int | None
    days_to_next_election: int | None
    approval_pct: float | None
    stability_pct: float | None
    corruption_pct: float | None
    crisis_status: str
    parties: tuple[PoliticalPartyView, ...]
    laws: tuple[PoliticalLawView, ...]
    pending_law_transitions: tuple[PoliticalLawTransitionView, ...]
    recent_causes: tuple[PoliticalCauseView, ...]
    election_override_options: tuple[PoliticalElectionOverrideOptionView, ...] = ()
    recent_elections: tuple[PoliticalElectionRecordView, ...] = ()


class PoliticalOverviewPresenter:
    """Projects political state from authoritative snapshot tables for read-only UI."""

    def build(self, state, country_tag: str) -> PoliticalOverviewViewModel:
        country_id = _tag(country_tag)
        country = self._one_for_country(state, "countries", country_id)
        government = self._one_for_country(state, "country_governments", country_id)
        now_minute = max(0, safe_int(getattr(getattr(state, "time", None), "total_minutes", 0)))

        form_name = safe_text(
            government.get("government_type"),
            safe_text(government.get("government_form_id"), "Unavailable"),
        )
        form_name = form_name or safe_text(government.get("government_form_id"), "Unavailable")
        ruling_id = _party_id(government.get("ruling_party_id"))
        party_rows = self._rows_for_country(state, "political_parties", country_id)
        ruling_row = next(
            (row for row in party_rows if _party_id(row.get("party_id")) == ruling_id),
            None,
        )
        ruling_party = safe_text(
            (ruling_row or {}).get("display_name"),
            ruling_id or "Unavailable",
        )

        election_eligible = _read_bool(government.get("election_eligible"))
        next_election = _optional_positive_int(government.get("next_election_at_minute"))
        form_rule = self._one_for_form(
            state,
            safe_text(government.get("government_form_id"), ""),
        )
        days_to_election = None
        if election_eligible and next_election is not None:
            days_to_election = max(0, math.ceil((next_election - now_minute) / MINUTES_PER_DAY))

        parties = tuple(
            sorted(
                (
                    PoliticalPartyView(
                        party_id=_party_id(row.get("party_id")),
                        display_name=safe_text(row.get("display_name"), _party_id(row.get("party_id"))),
                        support_pct=_as_percent(row.get("support_share")),
                        organization_pct=_as_percent(row.get("organization")),
                        eligible=_read_bool(row.get("eligible")),
                        is_ruling=_party_id(row.get("party_id")) == ruling_id,
                    )
                    for row in party_rows
                ),
                key=lambda party: (
                    -(party.support_pct if party.support_pct is not None else -1.0),
                    party.party_id,
                ),
            )
        )

        laws = tuple(
            PoliticalLawView(
                law_id=safe_text(row.get("law_id"), ""),
                group_name=safe_text(row.get("group_name"), "Other"),
                title=safe_text(row.get("title"), safe_text(row.get("law_id"), "Law")),
                status=safe_text(row.get("status"), "Unavailable"),
                value=safe_text(row.get("value"), "Unavailable"),
            )
            for row in sorted(
                self._rows_for_country(state, "country_laws", country_id),
                key=lambda item: (
                    safe_text(item.get("group_name"), ""),
                    safe_text(item.get("title"), ""),
                    safe_text(item.get("law_id"), ""),
                ),
            )
        )

        pending_transitions = tuple(
            PoliticalLawTransitionView(
                law_id=safe_text(row.get("law_id"), ""),
                target_value=safe_text(row.get("target_value"), "Unavailable"),
                effective_at_minute=safe_int(row.get("effective_at_minute")),
                status=safe_text(row.get("status"), "scheduled"),
            )
            for row in sorted(
                (
                    item
                    for item in self._rows_for_country(state, "law_transitions", country_id)
                    if safe_text(item.get("status"), "scheduled").lower() in {"pending", "scheduled"}
                ),
                key=lambda item: (safe_int(item.get("effective_at_minute")), safe_text(item.get("id"), "")),
            )
        )

        crisis_rows = self._rows_for_country(state, "political_crises", country_id)
        active_crises = sorted(
            (
                row
                for row in crisis_rows
                if safe_text(row.get("status"), "").lower() in {"pending", "active", "escalated"}
            ),
            key=lambda row: (-safe_int(row.get("created_at_minute")), safe_text(row.get("id"), "")),
        )
        crisis_status = safe_text(government.get("crisis_status"), "")
        if not crisis_status or crisis_status.lower() == "none":
            crisis_status = safe_text(active_crises[0].get("crisis_type"), "No active crisis") if active_crises else "No active crisis"

        recent_causes = tuple(
            PoliticalCauseView(
                game_minute=safe_int(row.get("game_minute")),
                event_type=safe_text(row.get("event_type"), "political event"),
                reason=safe_text(row.get("reason"), safe_text(row.get("result"), "Cause unavailable")),
                result=safe_text(row.get("result"), ""),
            )
            for row in sorted(
                self._rows_for_country(state, "political_history", country_id),
                key=lambda item: (-safe_int(item.get("game_minute")), safe_text(item.get("id"), "")),
            )[:8]
        )
        election_override_options = self._election_override_options(
            state,
            country_id,
            country,
            government,
            form_rule,
            now_minute,
        )
        recent_elections = self._recent_elections(state, country_id)

        return PoliticalOverviewViewModel(
            country_id=country_id,
            government_form=form_name,
            ruling_party=ruling_party,
            election_eligible=election_eligible,
            next_election_at_minute=next_election,
            days_to_next_election=days_to_election,
            approval_pct=_as_percent(country.get("gvt_approval")),
            stability_pct=_as_percent(country.get("gvt_stability")),
            corruption_pct=_as_percent(country.get("gvt_corruption")),
            crisis_status=crisis_status if government or crisis_rows else "Unavailable",
            parties=parties,
            laws=laws,
            pending_law_transitions=pending_transitions,
            recent_causes=recent_causes,
            election_override_options=election_override_options,
            recent_elections=recent_elections,
        )

    def _election_override_options(
        self,
        state,
        country_id: str,
        country: dict[str, Any],
        government: dict[str, Any],
        form_rule: dict[str, Any],
        now_minute: int,
    ) -> tuple[PoliticalElectionOverrideOptionView, ...]:
        rules = _decode_object_list(form_rule.get("election_overrides_json"))
        if not rules:
            return ()
        electoral = bool(_read_bool(government.get("election_eligible"))) and bool(
            _read_bool(form_rule.get("election_eligible"))
        )
        scheduled = sorted(
            (
                row
                for row in self._rows_for_country(state, "political_elections", country_id)
                if safe_text(row.get("status"), "").casefold() == "scheduled"
            ),
            key=lambda row: (
                safe_int(row.get("scheduled_at_minute")),
                safe_text(row.get("id"), ""),
            ),
        )
        current_date = (
            _optional_positive_int(scheduled[0].get("scheduled_at_minute"))
            if scheduled
            else _optional_positive_int(government.get("next_election_at_minute"))
        )
        crisis_status = safe_text(government.get("crisis_status"), "none").casefold()
        active_crisis = crisis_status not in {"", "none", "resolved"} or any(
            safe_text(row.get("status"), "").casefold() in {"pending", "active", "open"}
            for row in self._rows_for_country(state, "political_crises", country_id)
        )
        prior_overrides = [
            safe_int(row.get("game_minute"))
            for row in self._rows_for_country(state, "political_history", country_id)
            if safe_text(row.get("event_type"), "") == "election_override_applied"
        ]
        last_override = max(prior_overrides) if prior_overrides else None
        raw_funds = _finite_number(country.get("money_reserves"))
        supported = {"postpone", "accelerate", "suspend", "succession"}
        option_rules = [
            row
            for row in rules
            if str(row.get("type", row.get("override_type", ""))).strip().casefold()
            in supported
            and row.get("enabled", True) is not False
        ]
        type_counts: dict[str, int] = {}
        for row in option_rules:
            override_type = str(row.get("type", row.get("override_type", ""))).strip().casefold()
            type_counts[override_type] = type_counts.get(override_type, 0) + 1

        party_ids = {
            _party_id(row.get("party_id"))
            for row in self._rows_for_country(state, "political_parties", country_id)
        }
        options: list[PoliticalElectionOverrideOptionView] = []
        for rule in option_rules:
            override_type = str(rule.get("type", rule.get("override_type", ""))).strip().casefold()
            minimum = _bounded_integer(rule.get("minimum_duration_days", 1), 1, 36_500)
            maximum = _bounded_integer(rule.get("maximum_duration_days", 365), 1, 36_500)
            if minimum is None:
                minimum = 1
            if maximum is None:
                maximum = 0
            cost = _finite_number(rule.get("cost", 0.0))
            approval_delta = _finite_number(rule.get("approval_delta", 0.0))
            stability_delta = _finite_number(rule.get("stability_delta", 0.0))
            if approval_delta is None:
                approval_delta = 0.0
            if stability_delta is None:
                stability_delta = 0.0
            default_days = _bounded_integer(
                rule.get("default_duration_days", minimum), minimum, maximum
            ) if maximum >= minimum else minimum
            if default_days is None:
                default_days = minimum

            reason = ""
            if type_counts[override_type] != 1:
                reason = "Multiple rules define this override; it is unavailable."
            elif minimum <= 0 or maximum < minimum:
                reason = "The configured duration bounds are invalid."
            elif not electoral:
                reason = "This government does not hold scheduled elections."
            elif current_date is None:
                reason = "There is no scheduled election to override."
            elif active_crisis:
                reason = "Election overrides are unavailable during an active crisis."
            elif cost is None or cost < 0.0:
                reason = "The configured election override cost is invalid."
            elif raw_funds is None or raw_funds < cost:
                reason = "The country lacks funds for this election override."
            else:
                cooldown = _bounded_integer(rule.get("cooldown_days", 0), 0, 36_500)
                if cooldown is None:
                    reason = "The configured override cooldown is invalid."
                elif last_override is not None and now_minute < last_override + cooldown * MINUTES_PER_DAY:
                    reason = "The previous election override is still in cooldown."
                elif override_type == "accelerate":
                    notice = _bounded_integer(rule.get("minimum_notice_days", 1), 0, 36_500)
                    if notice is None or current_date <= now_minute + max(1, notice) * MINUTES_PER_DAY:
                        reason = "The election cannot be moved earlier within the legal date bounds."
                elif override_type == "suspend":
                    if now_minute + default_days * MINUTES_PER_DAY <= current_date:
                        first_effective_day = (
                            (current_date - now_minute) // MINUTES_PER_DAY
                        ) + 1
                        if first_effective_day > maximum:
                            reason = "The requested suspension would not change the election date."
                        else:
                            default_days = max(minimum, first_effective_day)
                elif override_type == "succession":
                    successor_id = _party_id(government.get("succession_party_id"))
                    if not successor_id or successor_id not in party_ids:
                        reason = "The configured succession party is unavailable."

            options.append(
                PoliticalElectionOverrideOptionView(
                    override_type=override_type,
                    minimum_duration_days=minimum,
                    maximum_duration_days=maximum,
                    default_duration_days=default_days,
                    cost=cost,
                    approval_delta=min(100.0, max(-100.0, approval_delta)),
                    stability_delta=min(100.0, max(-100.0, stability_delta)),
                    available=not reason,
                    unavailable_reason=reason,
                )
            )
        return tuple(sorted(options, key=lambda item: item.override_type))

    def _recent_elections(
        self,
        state,
        country_id: str,
    ) -> tuple[PoliticalElectionRecordView, ...]:
        return tuple(
            PoliticalElectionRecordView(
                status=safe_text(row.get("status"), "unavailable"),
                scheduled_at_minute=safe_int(row.get("scheduled_at_minute")),
                resolved_at_minute=safe_int(row.get("resolved_at_minute")),
                winner_party_id=_party_id(row.get("winner_party_id")),
                turnout_pct=_as_percent(row.get("turnout")),
                override_type=safe_text(row.get("override_type"), ""),
                reason=safe_text(row.get("reason"), ""),
            )
            for row in sorted(
                self._rows_for_country(state, "political_elections", country_id),
                key=lambda item: (
                    -safe_int(item.get("resolved_at_minute")),
                    -safe_int(item.get("scheduled_at_minute")),
                    safe_text(item.get("id"), ""),
                ),
            )[:5]
        )

    def _one_for_country(self, state, table_name: str, country_id: str) -> dict[str, Any]:
        rows = self._rows_for_country(state, table_name, country_id)
        return rows[0] if rows else {}

    def _rows_for_country(self, state, table_name: str, country_id: str) -> list[dict[str, Any]]:
        tables = getattr(state, "tables", {})
        frame = tables.get(table_name) if isinstance(tables, dict) else None
        country_key = "id" if table_name == "countries" else "country_id"
        if frame is None or frame.is_empty() or country_key not in frame.columns:
            return []
        return [
            row
            for row in frame.iter_rows(named=True)
            if _tag(row.get(country_key)) == country_id
        ]

    def _one_for_form(self, state, form_id: str) -> dict[str, Any]:
        target = _form_id(form_id)
        frame = getattr(state, "tables", {}).get("government_form_rules")
        if frame is None or frame.is_empty() or "government_form_id" not in frame.columns:
            return {}
        return next(
            (
                row
                for row in frame.iter_rows(named=True)
                if _form_id(row.get("government_form_id")) == target
            ),
            {},
        )


def _as_percent(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    if 0.0 <= number <= 1.0:
        number *= 100.0
    return min(100.0, max(0.0, number))


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _read_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()


def _party_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _form_id(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _decode_object_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        parsed = value
    else:
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    return [dict(item) for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _bounded_integer(value: Any, minimum: int, maximum: int) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        return None
    return number if minimum <= number <= maximum else None
