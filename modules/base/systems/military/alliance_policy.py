"""Direct military-alliance eligibility for tactical battles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl


@dataclass(frozen=True, slots=True)
class AllianceEligibility:
    side_a: frozenset[str]
    side_b: frozenset[str]
    roles: dict[str, str]
    bases: dict[str, str]
    rejected: tuple[tuple[str, str], ...]


class AlliancePolicy:
    """Expands only direct active military/defensive treaty commitments."""

    _MILITARY_TYPES = frozenset({
        "alliance", "defensive_alliance", "military_alliance", "mutual_defense",
        "defense_pact", "military_pact",
    })

    def expand(self, war: Any, local_units: list[dict[str, Any]], treaties: pl.DataFrame | None) -> AllianceEligibility:
        side_a = {self._tag(value) for value in getattr(war, "side_a", ()) if self._tag(value)}
        side_b = {self._tag(value) for value in getattr(war, "side_b", ()) if self._tag(value)}
        roles = {tag: "principal" for tag in side_a | side_b}
        bases = {tag: "war_side" for tag in side_a | side_b}
        present = sorted({self._tag(row.get("owner")) for row in local_units if self._tag(row.get("owner"))})
        rejected: list[tuple[str, str]] = []

        if treaties is not None and not treaties.is_empty():
            rows = sorted(
                treaties.to_dicts(),
                key=lambda row: (str(row.get("id") or ""), str(row.get("type") or row.get("treaty_type") or "")),
            )
            for country in present:
                if country in side_a or country in side_b:
                    continue
                candidate_sides: list[tuple[str, str]] = []
                for row in rows:
                    if str(row.get("status") or "").lower() != "active":
                        continue
                    treaty_type = str(row.get("type") or row.get("treaty_type") or "").strip().lower()
                    if treaty_type not in self._MILITARY_TYPES:
                        continue
                    members = self._tags(row.get("members"))
                    treaty_a = self._tags(row.get("side_a"))
                    treaty_b = self._tags(row.get("side_b"))
                    if not members:
                        members = treaty_a | treaty_b
                    if country not in members:
                        continue
                    # A direct military pact can assist only when the pact
                    # contains a principal on exactly one side of this war.
                    if members & side_a and not members & side_b:
                        candidate_sides.append(("a", str(row.get("id") or treaty_type)))
                    elif members & side_b and not members & side_a:
                        candidate_sides.append(("b", str(row.get("id") or treaty_type)))
                    elif country in treaty_a and treaty_a & side_a and not treaty_b & side_b:
                        candidate_sides.append(("a", str(row.get("id") or treaty_type)))
                    elif country in treaty_b and treaty_b & side_b and not treaty_a & side_a:
                        candidate_sides.append(("b", str(row.get("id") or treaty_type)))
                if len({side for side, _ in candidate_sides}) == 1:
                    side, basis = candidate_sides[0]
                    (side_a if side == "a" else side_b).add(country)
                    roles[country] = "ally"
                    bases[country] = f"treaty:{basis}"
                elif candidate_sides:
                    rejected.append((country, "ambiguous_alliance"))
                else:
                    rejected.append((country, "no_direct_active_military_alliance"))

        # Countries present in neither resolved side are intentionally omitted.
        for country in present:
            if country not in side_a and country not in side_b and (country, "no_direct_active_military_alliance") not in rejected and (country, "ambiguous_alliance") not in rejected:
                rejected.append((country, "not_in_war"))
        return AllianceEligibility(frozenset(side_a), frozenset(side_b), roles, bases, tuple(sorted(rejected)))

    def _tags(self, value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, str):
            return {self._tag(part) for part in value.split(",") if self._tag(part)}
        if isinstance(value, (list, tuple, set)):
            return {self._tag(part) for part in value if self._tag(part)}
        return set()

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()
