"""Pure policies for initializing and validating persistent political state."""

from __future__ import annotations

import math
from typing import Any

import polars as pl


GAME_MINUTES_PER_YEAR = 365 * 24 * 60
DEFAULT_ELECTION_INTERVAL_MINUTES = 4 * GAME_MINUTES_PER_YEAR

_DEFAULT_FORM_RULES = (
    {
        "government_form_id": "multi-party democracy",
        "display_name": "Multi-party democracy",
        "election_eligible": True,
        "election_interval_minutes": DEFAULT_ELECTION_INTERVAL_MINUTES,
        "law_permissions_json": '["*"]',
    },
    {
        "government_form_id": "centralized republic",
        "display_name": "Centralized republic",
        "election_eligible": True,
        "election_interval_minutes": DEFAULT_ELECTION_INTERVAL_MINUTES,
        "law_permissions_json": '["*"]',
    },
    {
        "government_form_id": "transitional republic",
        "display_name": "Transitional republic",
        "election_eligible": True,
        "election_interval_minutes": DEFAULT_ELECTION_INTERVAL_MINUTES,
        "law_permissions_json": '["*"]',
    },
    {
        "government_form_id": "military-led state",
        "display_name": "Military-led state",
        "election_eligible": False,
        "election_interval_minutes": 0,
        "law_permissions_json": '["*"]',
    },
    {
        "government_form_id": "emergency administration",
        "display_name": "Emergency administration",
        "election_eligible": False,
        "election_interval_minutes": 0,
        "law_permissions_json": '["*"]',
    },
)


def default_government_form_rules(existing: pl.DataFrame | None) -> pl.DataFrame:
    """Add default form rules without overwriting scenario- or mod-owned rules."""

    current = _rows_by_key(existing, "government_form_id")
    additions = [
        _form_rule(row)
        for row in _DEFAULT_FORM_RULES
        if _form_id(row["government_form_id"]) not in current
    ]
    if not additions:
        return existing if existing is not None else pl.DataFrame()
    return _append_rows(existing, additions)


def initialize_country_politics(
    countries: pl.DataFrame | None,
    governments: pl.DataFrame | None,
    parties: pl.DataFrame | None,
    form_rules: pl.DataFrame | None,
    now_minute: int,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Create valid legacy defaults once while preserving initialized state."""

    if countries is None or countries.is_empty() or "id" not in countries.columns:
        return _empty_like(governments), _empty_like(parties), form_rules if form_rules is not None else pl.DataFrame()

    government_rows = _rows_by_key(governments, "country_id")
    party_rows = _rows_by_composite_key(parties, "country_id", "party_id")
    rules = _rows_by_key(form_rules, "government_form_id")
    selected_governments: list[dict[str, Any]] = []
    selected_parties: dict[tuple[str, str], dict[str, Any]] = dict(party_rows)

    for country in countries.sort("id").iter_rows(named=True):
        country_id = _tag(country.get("id"))
        if not country_id:
            continue
        government = dict(government_rows.get(country_id, {}))
        display_name = _text(government.get("government_type"), "Transitional republic")
        form_id = _form_id(government.get("government_form_id")) or _form_id(display_name)
        rule = rules.get(form_id)
        if rule is None:
            rule = _form_rule(
                {
                    "government_form_id": form_id,
                    "display_name": display_name,
                    "election_eligible": False,
                    "election_interval_minutes": 0,
                }
            )
            rules[form_id] = rule

        initialized = bool(government.get("initialized", False))
        election_eligible = (
            bool(government.get("election_eligible", False))
            if initialized
            else bool(rule.get("election_eligible", False))
        )
        interval = _non_negative_int(rule.get("election_interval_minutes"))
        if election_eligible and interval == 0:
            interval = DEFAULT_ELECTION_INTERVAL_MINUTES
        next_election = _non_negative_int(government.get("next_election_at_minute"))
        if not election_eligible:
            next_election = 0
        elif next_election <= 0:
            next_election = max(0, int(now_minute)) + interval

        country_parties = {
            party_id: row
            for (party_country, party_id), row in selected_parties.items()
            if party_country == country_id
        }
        ruling_party_id = _party_id(government.get("ruling_party_id"))
        if ruling_party_id not in country_parties:
            ruling_parties = sorted(
                party_id
                for party_id, row in country_parties.items()
                if bool(row.get("is_ruling", False))
            )
            ruling_party_id = ruling_parties[0] if ruling_parties else "incumbent"
        if ruling_party_id not in country_parties:
            incumbent = {
                "country_id": country_id,
                "party_id": ruling_party_id,
                "display_name": "Incumbent",
                "support_share": 1.0,
                "organization": 0.5,
                "policy_positions_json": "{}",
                "eligible": True,
                "is_ruling": True,
                "updated_at_minute": max(0, int(now_minute)),
            }
            selected_parties[(country_id, ruling_party_id)] = incumbent
            country_parties[ruling_party_id] = incumbent
        for party_id, party in list(country_parties.items()):
            selected_parties[(country_id, party_id)] = {
                **party,
                "is_ruling": party_id == ruling_party_id,
            }

        government.update(
            {
                "country_id": country_id,
                "government_type": display_name,
                "government_form_id": form_id,
                "ruling_party_id": ruling_party_id,
                "election_eligible": election_eligible,
                "next_election_at_minute": next_election,
                "succession_party_id": _party_id(government.get("succession_party_id")) or ruling_party_id,
                "crisis_status": _text(government.get("crisis_status"), "none") or "none",
                "initialized": True,
                "last_election_id": _text(government.get("last_election_id"), ""),
                "updated_at_minute": (
                    _non_negative_int(government.get("updated_at_minute"))
                    if initialized
                    else max(0, int(now_minute))
                ),
            }
        )
        selected_governments.append(government)

    next_rules = list(rules.values())
    return (
        _frame_like(governments, selected_governments),
        _frame_like(parties, list(selected_parties.values())),
        _frame_like(form_rules, next_rules),
    )


def normalize_political_indicators(countries: pl.DataFrame) -> pl.DataFrame:
    """Keep the three political indicators bounded without conflating their causes."""

    defaults = {
        "gvt_approval": 50.0,
        "gvt_stability": 50.0,
        "gvt_corruption": 10.0,
    }
    expressions = []
    for column, default in defaults.items():
        if column not in countries.columns:
            continue
        value = pl.col(column).cast(pl.Float64, strict=False)
        finite = pl.when(value.is_finite()).then(value).otherwise(default).fill_null(default)
        fraction = finite.is_between(0.0, 1.0, closed="both")
        percentage = pl.when(fraction).then(finite * 100.0).otherwise(finite)
        expressions.append(percentage.clip(0.0, 100.0).alias(column))
    return countries.with_columns(expressions) if expressions else countries


def clamp_percent(value: Any, default: float = 0.0) -> float:
    """Normalize finite percentage inputs into the inclusive 0–100 range."""

    number = _finite(value, default)
    if 0.0 <= number <= 1.0:
        number *= 100.0
    return min(100.0, max(0.0, number))


def _form_rule(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "government_form_id": _form_id(values.get("government_form_id")),
        "display_name": _text(values.get("display_name"), _text(values.get("government_form_id"), "")),
        "election_eligible": bool(values.get("election_eligible", False)),
        "election_interval_minutes": _non_negative_int(values.get("election_interval_minutes")),
        "election_turnout_base": _finite(values.get("election_turnout_base"), 0.65),
        "election_turnout_approval_weight": _finite(
            values.get("election_turnout_approval_weight"), 0.003
        ),
        "election_turnout_stability_weight": _finite(
            values.get("election_turnout_stability_weight"), 0.002
        ),
        "incumbent_advantage": _finite(values.get("incumbent_advantage"), 0.1),
        "coalition_threshold": _finite(values.get("coalition_threshold"), 0.5),
        "succession_rule": _text(values.get("succession_rule"), "incumbent_fallback"),
        "party_participation_json": _text(values.get("party_participation_json"), "[]"),
        "law_permissions_json": _text(values.get("law_permissions_json"), "[]"),
        "election_overrides_json": _text(values.get("election_overrides_json"), "[]"),
        "crisis_rules_json": _text(values.get("crisis_rules_json"), "{}"),
        "regime_change_paths_json": _text(values.get("regime_change_paths_json"), "[]"),
    }


def _rows_by_key(frame: pl.DataFrame | None, key: str) -> dict[str, dict[str, Any]]:
    if frame is None or frame.is_empty() or key not in frame.columns:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in frame.iter_rows(named=True):
        normalized = _form_id(row.get(key)) if key == "government_form_id" else _tag(row.get(key))
        if normalized and normalized not in result:
            result[normalized] = dict(row)
    return result


def _rows_by_composite_key(
    frame: pl.DataFrame | None,
    first_key: str,
    second_key: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    if frame is None or frame.is_empty() or not {first_key, second_key}.issubset(frame.columns):
        return {}
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in frame.iter_rows(named=True):
        key = (_tag(row.get(first_key)), _party_id(row.get(second_key)))
        if all(key) and key not in result:
            result[key] = dict(row)
    return result


def _append_rows(frame: pl.DataFrame | None, rows: list[dict[str, Any]]) -> pl.DataFrame:
    if frame is None or not frame.columns:
        return pl.DataFrame(rows) if rows else pl.DataFrame()
    additions = pl.DataFrame(rows, schema=frame.schema, strict=False)
    return pl.concat([frame, additions], how="vertical_relaxed")


def _frame_like(frame: pl.DataFrame | None, rows: list[dict[str, Any]]) -> pl.DataFrame:
    if frame is None or not frame.columns:
        return pl.DataFrame(rows) if rows else pl.DataFrame()
    return pl.DataFrame(rows, schema=frame.schema, strict=False) if rows else frame.clear()


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()


def _form_id(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _party_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _text(value: Any, default: str) -> str:
    return str(value if value is not None else default).strip()


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _finite(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def _empty_like(frame: pl.DataFrame | None) -> pl.DataFrame:
    return frame if frame is not None else pl.DataFrame()
