"""Pure policy rules for language and religious identity distributions."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


IDENTITY_STATUSES = ("official", "legal", "restricted", "illegal")
IDENTITY_TYPES = ("language", "religion")
_MINUTES_PER_DAY = 24 * 60
_DAYS_PER_YEAR = 365.25
_ANNUAL_SHIFT_RATE = {"restricted": 0.005, "illegal": 0.02}


def normalize_identity_status(value: Any) -> str:
    status = str(value or "").strip().casefold()
    return status if status in IDENTITY_STATUSES else ""


def calculate_identity_signals(groups: list[dict[str, Any]]) -> dict[str, float | int]:
    """Summarizes recognition and restriction pressure as percentage shares."""
    language_rows = [row for row in groups if _type(row) == "language"]
    religion_rows = [row for row in groups if _type(row) == "religion"]
    dimensions = [rows for rows in (language_rows, religion_rows) if rows]
    official = restricted = illegal = rights_signal = 0.0
    for rows in dimensions:
        dimension_official = dimension_restricted = dimension_illegal = 0.0
        for row in rows:
            share = _share(row.get("population_share"))
            status = normalize_identity_status(row.get("legal_status")) or "legal"
            if status == "official":
                dimension_official += share
            elif status == "restricted":
                dimension_restricted += share
            elif status == "illegal":
                dimension_illegal += share
        official += min(100.0, dimension_official)
        restricted += min(100.0, dimension_restricted)
        illegal += min(100.0, dimension_illegal)
        rights_signal += min(
            1.0,
            max(-1.0, (dimension_official * 0.1 - dimension_restricted * 0.5 - dimension_illegal) / 100.0),
        )
    divisor = float(len(dimensions)) if dimensions else 1.0
    official /= divisor
    restricted /= divisor
    illegal /= divisor
    pressure = min(100.0, max(0.0, illegal + restricted * 0.5))
    rights_signal = min(1.0, max(-1.0, rights_signal / divisor))
    return {
        "language_group_count": len(language_rows),
        "religion_group_count": len(religion_rows),
        "official_share": min(100.0, official),
        "restricted_share": min(100.0, restricted),
        "illegal_share": min(100.0, illegal),
        "policy_pressure": pressure,
        "rights_signal": rights_signal,
    }


def apply_identity_assimilation(
    groups: list[dict[str, Any]], now_minute: int
) -> list[dict[str, Any]]:
    """Gradually reallocates restricted self-identification to a permitted group."""
    by_profile: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in groups:
        by_profile[(_country(row.get("country_id")), _type(row))].append(row)

    changes: list[dict[str, Any]] = []
    for (country_id, identity_type), rows in by_profile.items():
        suppressed = [
            row for row in rows if normalize_identity_status(row.get("legal_status")) in _ANNUAL_SHIFT_RATE
        ]
        if not suppressed:
            continue

        eligible = [
            row
            for row in rows
            if normalize_identity_status(row.get("legal_status")) in {"official", "legal"}
        ]
        if not eligible:
            continue
        eligible.sort(
            key=lambda row: (
                bool(row.get("is_other_bucket")),
                -_share(row.get("population_share")),
                str(row.get("identity_id") or ""),
            )
        )
        destination = eligible[0]
        elapsed_by_row = []
        for row in suppressed:
            try:
                previous_minute = int(row.get("last_updated_minute") or 0)
            except (TypeError, ValueError, OverflowError):
                previous_minute = 0
            elapsed_days = max(0.0, (int(now_minute) - previous_minute) / _MINUTES_PER_DAY)
            status = normalize_identity_status(row.get("legal_status"))
            annual_rate = _ANNUAL_SHIFT_RATE[status]
            shifted_share = _share(row.get("population_share")) * (
                1.0 - math.pow(1.0 - annual_rate, elapsed_days / _DAYS_PER_YEAR)
            )
            elapsed_by_row.append((row, max(0.0, shifted_share)))

        total_shift = 0.0
        for row, shifted_share in elapsed_by_row:
            row["population_share"] = max(0.0, _share(row.get("population_share")) - shifted_share)
            row["last_updated_minute"] = max(0, int(now_minute))
            if shifted_share >= 0.0001:
                changes.append(
                    {
                        "country_id": country_id,
                        "identity_type": identity_type,
                        "source_identity_id": str(row.get("identity_id") or ""),
                        "destination_identity_id": str(destination.get("identity_id") or ""),
                        "share_points": shifted_share,
                    }
                )
                total_shift += shifted_share
        if total_shift > 0.0:
            destination["population_share"] = _share(destination.get("population_share")) + total_shift
            destination["last_updated_minute"] = max(0, int(now_minute))

    return changes


def _country(value: Any) -> str:
    return str(value or "").strip().upper()


def _type(row: dict[str, Any]) -> str:
    return str(row.get("identity_type") or "").strip().casefold()


def _share(value: Any) -> float:
    try:
        share = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return min(100.0, max(0.0, share)) if math.isfinite(share) else 0.0
