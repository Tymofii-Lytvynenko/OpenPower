"""Pure policy helpers for recognition eligibility and regional access."""

from __future__ import annotations

from typing import Any

import polars as pl


def is_un_member(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def eligible_voters(
    countries: pl.DataFrame | None,
    claimant_id: str,
    former_owner_id: str,
) -> tuple[str, ...]:
    if countries is None or countries.is_empty() or "id" not in countries.columns:
        return ()
    claimant = _tag(claimant_id)
    former_owner = _tag(former_owner_id)
    if "un_member" not in countries.columns:
        return ()
    return tuple(
        sorted(
            {
                _tag(row.get("id"))
                for row in countries.iter_rows(named=True)
                if _tag(row.get("id"))
                and _tag(row.get("id")) not in {claimant, former_owner}
                and is_un_member(row.get("un_member"))
            }
        )
    )


def ai_recognition_vote(
    state: Any,
    voter_id: str,
    claimant_id: str,
) -> str:
    """Prefer recognition with constructive ties; oppose active-war claims."""

    return RecognitionAIPolicy(state).vote(voter_id, claimant_id)


class RecognitionAIPolicy:
    """Indexes diplomatic signals once so large daily vote batches stay bounded."""

    def __init__(self, state: Any) -> None:
        self._relations: dict[tuple[str, str], list[float]] = {}
        relations = state.tables.get("countries_relations")
        if relations is not None and not relations.is_empty() and {"source", "target", "value"}.issubset(relations.columns):
            for row in relations.iter_rows(named=True):
                left, right = _tag(row.get("source")), _tag(row.get("target"))
                try:
                    value = float(row.get("value"))
                except (TypeError, ValueError, OverflowError):
                    continue
                if left and right:
                    self._relations.setdefault((left, right), []).append(value)

        wars = state.tables.get("countries_wars")
        self._active_wars: set[frozenset[str]] = set()
        if wars is not None and not wars.is_empty():
            for row in wars.iter_rows(named=True):
                if str(row.get("status") or "active").lower() not in {"active", "war", "ongoing"}:
                    continue
                side_a = set()
                side_b = set()
                for key in ("attacker", "attacker_id", "country_a", "side_a", "attacker_countries"):
                    side_a.update(_country_tags(row.get(key)))
                for key in ("defender", "defender_id", "country_b", "side_b", "defender_countries"):
                    side_b.update(_country_tags(row.get(key)))
                self._active_wars.update(
                    frozenset((left, right))
                    for left in side_a
                    for right in side_b
                    if left and right and left != right
                )

        self._treaty_bonus: dict[tuple[str, str], float] = {}
        treaties = state.tables.get("countries_treaties")
        if treaties is not None and not treaties.is_empty():
            for treaty in treaties.iter_rows(named=True):
                if str(treaty.get("status") or "active").strip().lower() != "active":
                    continue
                members = _country_tags(treaty.get("members"))
                if not members:
                    members = _country_tags(treaty.get("side_a")) | _country_tags(treaty.get("side_b"))
                kind = str(treaty.get("type") or treaty.get("treaty_type") or "").lower()
                bonus = 25.0 if kind in {"alliance", "common_market"} else 15.0 if kind in {"economic_partnership", "economic_union"} else 0.0
                if bonus <= 0.0:
                    continue
                ordered_members = sorted(members)
                for left_index, left in enumerate(ordered_members):
                    for right in ordered_members[left_index + 1 :]:
                        self._treaty_bonus[(left, right)] = self._treaty_bonus.get((left, right), 0.0) + bonus
                        self._treaty_bonus[(right, left)] = self._treaty_bonus.get((right, left), 0.0) + bonus

    def vote(self, voter_id: str, claimant_id: str) -> str:
        voter = _tag(voter_id)
        claimant = _tag(claimant_id)
        values = self._relations.get((voter, claimant), []) + self._relations.get((claimant, voter), [])
        relation = sum(values) / len(values) if values else 0.0
        score = 50.0 + relation * 0.25 + self._treaty_bonus.get((voter, claimant), 0.0)
        if frozenset((voter, claimant)) in self._active_wars:
            score -= 100.0
        return "yes" if score >= 50.0 else "no"


def regional_economic_access_allowed(
    state: Any,
    region_id: int,
    country_id: str,
) -> bool:
    """Require owner-controlled domestic access or current foreign recognition."""

    regions = state.tables.get("regions")
    if regions is None or regions.is_empty() or not {"id", "owner"}.issubset(regions.columns):
        return False
    matches = regions.filter(pl.col("id") == int(region_id))
    if matches.is_empty():
        return False
    region = matches.row(0, named=True)
    owner = _tag(region.get("owner"))
    controller = _region_controller(region, owner)
    country = _tag(country_id)
    if country and owner == country and controller == country:
        return True
    if not owner or controller != owner:
        return False
    records = state.tables.get("regional_recognition_status")
    cases = state.tables.get("recognition_cases")
    if (
        records is None
        or records.is_empty()
        or cases is None
        or cases.is_empty()
    ):
        return False
    required_status_columns = {
        "region_id",
        "country_id",
        "claimant_id",
        "case_id",
        "status",
    }
    required_case_columns = {"id", "region_id", "claimant_id", "status"}
    if (
        not required_status_columns.issubset(records.columns)
        or not required_case_columns.issubset(cases.columns)
    ):
        return False
    active_cases = cases.filter(
        (pl.col("region_id") == int(region_id))
        & (pl.col("claimant_id") == owner)
        & (pl.col("status") == "passed")
    )
    active_case_ids = active_cases.get_column("id").to_list()
    if not active_case_ids:
        return False

    active_statuses = records.filter(
        (pl.col("region_id") == int(region_id))
        & (pl.col("country_id") == country)
        & (pl.col("claimant_id") == owner)
        & pl.col("case_id").is_in(active_case_ids)
        & (pl.col("status") == "recognized")
    )
    if "withdrawn_at_minute" in active_statuses.columns:
        active_statuses = active_statuses.filter(pl.col("withdrawn_at_minute") == 0)
    return not active_statuses.is_empty()


def regional_trade_access_allowed(
    state: Any,
    region_id: int,
    exporter_id: str,
    importer_id: str,
) -> bool:
    """Gate explicitly sourced trade only while a current recognition claim exists."""

    regions = state.tables.get("regions")
    if regions is None or regions.is_empty() or not {"id", "owner"}.issubset(regions.columns):
        return False
    matches = regions.filter(pl.col("id") == int(region_id))
    if matches.is_empty():
        return False

    region = matches.row(0, named=True)
    owner = _tag(region.get("owner"))
    controller = _region_controller(region, owner)
    exporter = _tag(exporter_id)
    importer = _tag(importer_id)
    if not owner or controller != owner or exporter != owner:
        return False
    if importer == owner:
        return True

    cases = state.tables.get("recognition_cases")
    has_current_case = False
    if cases is not None and not cases.is_empty() and {"region_id", "claimant_id", "status"}.issubset(cases.columns):
        has_current_case = not cases.filter(
            (pl.col("region_id") == int(region_id))
            & (pl.col("claimant_id") == owner)
            & pl.col("status").is_in(["pending", "passed", "rejected"])
        ).is_empty()

    statuses = state.tables.get("regional_recognition_status")
    has_current_status = False
    if statuses is not None and not statuses.is_empty() and {"region_id", "claimant_id"}.issubset(statuses.columns):
        current_statuses = statuses.filter(
            (pl.col("region_id") == int(region_id))
            & (pl.col("claimant_id") == owner)
        )
        if "withdrawn_at_minute" in current_statuses.columns:
            current_statuses = current_statuses.filter(pl.col("withdrawn_at_minute") == 0)
        has_current_status = not current_statuses.is_empty()

    if not has_current_case and not has_current_status:
        return True
    return regional_economic_access_allowed(state, int(region_id), importer)


def _region_controller(region: dict[str, Any], owner: str) -> str:
    # Seeded maps may omit controller; territory policy treats those regions as owner-controlled.
    return _tag(region.get("controller") or owner)


def _country_tags(value: Any) -> set[str]:
    if value is None:
        return set()
    values = value if isinstance(value, (list, tuple, set)) else str(value).split(",")
    return {_tag(item) for item in values if _tag(item)}


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()
