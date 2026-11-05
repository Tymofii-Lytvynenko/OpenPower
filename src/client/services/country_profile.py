from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ProfileMetric:
    label: str
    column: str
    default_value: float


# Missing snapshot fields follow OpenPower's country and politics defaults.
PROFILE_METRICS = {
    "economic": ProfileMetric("Economic (GDP)", "gdp", 10_000_000.0),
    "political": ProfileMetric("Political (government approval)", "gvt_approval", 50.0),
    "military": ProfileMetric("Military (personnel)", "military_count", 0.0),
}


@dataclass(frozen=True, slots=True)
class CountryProfileCandidate:
    country_id: str
    name: str
    economic_rank: int
    political_rank: int
    military_rank: int
    distance: float

    def rank_for(self, metric: str) -> int:
        return {
            "economic": self.economic_rank,
            "political": self.political_rank,
            "military": self.military_rank,
        }[metric]


def suggest_country_profiles(
    country_rows: list[Mapping[str, object]],
    desired_values: Mapping[str, float],
    enabled_metrics: Mapping[str, bool],
    *,
    limit: int = 10,
) -> list[CountryProfileCandidate]:
    """Rank eligible countries against explicit OpenPower economic, political, and military data."""
    normalized = [
        row for row in country_rows
        if str(row.get("id") or "").strip()
    ]
    if not normalized:
        return []

    tags = [str(row["id"]).strip().upper() for row in normalized]
    values = {
        metric: {
            tag: _finite_float(row.get(profile_metric.column), default=profile_metric.default_value)
            for tag, row in zip(tags, normalized)
        }
        for metric, profile_metric in PROFILE_METRICS.items()
    }
    ranks = {
        metric: {
            tag: index
            for index, (tag, _) in enumerate(
                sorted(metric_values.items(), key=lambda item: (-item[1], item[0])),
                start=1,
            )
        }
        for metric, metric_values in values.items()
    }

    active_metrics = [
        metric for metric in PROFILE_METRICS
        if bool(enabled_metrics.get(metric, False))
    ]
    country_count = len(tags)
    wanted_ranks = {
        metric: max(
            1,
            min(
                country_count,
                math.floor((1.0 - _bounded_ratio(desired_values.get(metric, 0.5))) * country_count),
            ),
        )
        for metric in active_metrics
    }

    scored = []
    for row, tag in zip(normalized, tags):
        distance = (
            sum(abs(wanted_ranks[metric] - ranks[metric][tag]) for metric in active_metrics)
            / len(active_metrics)
            if active_metrics
            else -1.0
        )
        scored.append(
            CountryProfileCandidate(
                country_id=tag,
                name=str(row.get("name") or tag),
                economic_rank=ranks["economic"][tag],
                political_rank=ranks["political"][tag],
                military_rank=ranks["military"][tag],
                distance=distance,
            )
        )

    return sorted(scored, key=lambda candidate: (candidate.distance, candidate.country_id))[:max(0, limit)]


def _finite_float(value: object, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _bounded_ratio(value: object) -> float:
    return max(0.0, min(1.0, _finite_float(value, default=0.0)))
