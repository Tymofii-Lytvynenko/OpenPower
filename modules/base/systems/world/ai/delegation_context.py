from dataclasses import dataclass, field
import json
from typing import Any

from src.shared.state import GameState


@dataclass(frozen=True, slots=True)
class _DelegationScope:
    scope_type: str
    scope_id: str
    sphere_members: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class _ResolvedDelegation:
    country: str
    scope: _DelegationScope
    authority: frozenset[str]


@dataclass(slots=True)
class _DelegationAccumulator:
    delegated: dict[str, set[str]] = field(default_factory=dict)
    unrestricted: dict[str, set[str]] = field(default_factory=dict)
    targets: dict[str, set[str]] = field(default_factory=dict)
    treaty_ids: dict[str, set[str]] = field(default_factory=dict)

    def add(self, delegation: _ResolvedDelegation) -> None:
        country = delegation.country
        authority = delegation.authority
        self.delegated.setdefault(country, set()).update(authority)
        if delegation.scope.scope_type == "country":
            self.unrestricted.setdefault(country, set()).update(authority)
        elif delegation.scope.scope_type == "sphere" and "diplomacy" in authority:
            self.targets.setdefault(country, set()).update(
                delegation.scope.sphere_members - {country}
            )
            self.treaty_ids.setdefault(country, set()).add(delegation.scope.scope_id)

    def freeze(self) -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]], dict[str, frozenset[str]]]:
        self._remove_redundant_sphere_targets()
        return (
            {country: frozenset(domains) for country, domains in self.delegated.items() if domains},
            {country: frozenset(countries) for country, countries in self.targets.items()},
            {country: frozenset(ids) for country, ids in self.treaty_ids.items()},
        )

    def _remove_redundant_sphere_targets(self) -> None:
        for country, authority in self.unrestricted.items():
            if "diplomacy" in authority:
                self.targets.pop(country, None)
                self.treaty_ids.pop(country, None)


class _DelegationScopePolicy:
    def __init__(
        self,
        governments: dict[str, str],
        treaties: dict[str, dict[str, Any]],
    ) -> None:
        self._governments = governments
        self._treaties = treaties

    def resolve(self, scope_type: str, scope_id: str, country: str) -> _DelegationScope | None:
        if scope_type == "country":
            if scope_id.upper() != country:
                return None
            return _DelegationScope(scope_type, scope_id)
        if scope_type == "party":
            if not scope_id or self._governments.get(country) != scope_id.casefold():
                return None
            return _DelegationScope(scope_type, scope_id)
        if scope_type == "sphere":
            return self._resolve_sphere(scope_id, country)
        return None

    def _resolve_sphere(self, scope_id: str, country: str) -> _DelegationScope | None:
        treaty = self._treaties.get(scope_id)
        if treaty is None or str(treaty.get("status") or "active").strip().lower() != "active":
            return None
        members = self._sphere_members(treaty)
        if members is None or country not in members or len(members) < 2:
            return None
        return _DelegationScope("sphere", scope_id, members)

    @staticmethod
    def _sphere_members(treaty: dict[str, Any]) -> frozenset[str] | None:
        members = treaty.get("members") or []
        if isinstance(members, str):
            try:
                members = json.loads(members)
            except (TypeError, ValueError):
                members = []
        if not isinstance(members, (list, tuple, set)):
            return None
        return frozenset(str(item).strip().upper() for item in members if str(item).strip())


class DelegationContextBuilder:
    """Build immutable AI authority and diplomacy targets from current game tables."""

    def build(
        self,
        state: GameState,
    ) -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]], dict[str, frozenset[str]]]:
        delegations = state.tables.get("sphere_delegations")
        if delegations is None or delegations.is_empty():
            return {}, {}, {}

        governments = self._governments_by_ruling_party(state)
        treaties = self._treaties_by_id(state)
        scope_policy = _DelegationScopePolicy(governments, treaties)
        accumulator = _DelegationAccumulator()
        for row in delegations.to_dicts():
            resolved = self._resolve_delegation(row, scope_policy)
            if resolved is not None:
                accumulator.add(resolved)
        return accumulator.freeze()

    @staticmethod
    def _governments_by_ruling_party(state: GameState) -> dict[str, str]:
        governments_table = state.tables.get("country_governments")
        governments = {
            str(row.get("country_id") or "").strip().upper(): str(
                row.get("ruling_party_id") or ""
            ).strip().casefold()
            for row in (governments_table.to_dicts() if governments_table is not None else [])
        }
        parties = state.tables.get("political_parties")
        DelegationContextBuilder._fill_missing_ruling_parties(governments, parties)
        return governments

    @staticmethod
    def _fill_missing_ruling_parties(governments: dict[str, str], parties: Any) -> None:
        if parties is None:
            return
        for row in parties.to_dicts():
            country = str(row.get("country_id") or "").strip().upper()
            if bool(row.get("is_ruling")) and country and not governments.get(country):
                governments[country] = str(row.get("party_id") or "").strip().casefold()

    @staticmethod
    def _treaties_by_id(state: GameState) -> dict[str, dict[str, Any]]:
        treaties = state.tables.get("countries_treaties")
        if treaties is None:
            return {}
        return {str(row.get("id") or ""): row for row in treaties.to_dicts()}

    def _resolve_delegation(
        self,
        row: dict[str, Any],
        scope_policy: _DelegationScopePolicy,
    ) -> _ResolvedDelegation | None:
        country = self._active_ai_owner(row)
        if country is None:
            return None
        scope_type = str(row.get("scope_type") or "country").strip().lower()
        scope_id = str(row.get("scope_id") or "").strip()
        scope = scope_policy.resolve(scope_type, scope_id, country)
        if scope is None:
            return None
        authority = self._authority(row)
        if authority is None:
            return None
        return _ResolvedDelegation(country, scope, authority)

    @staticmethod
    def _active_ai_owner(row: dict[str, Any]) -> str | None:
        country = str(row.get("owner_country_id") or "").strip().upper()
        if not country or not bool(row.get("active")):
            return None
        if str(row.get("current_controller") or "").strip().lower() != "ai":
            return None
        return country

    @staticmethod
    def _authority(row: dict[str, Any]) -> frozenset[str] | None:
        try:
            raw_authority = json.loads(row.get("authority_json") or "[]")
        except (TypeError, ValueError):
            return None
        if not isinstance(raw_authority, list):
            return None
        authority = frozenset(
            str(item).strip().lower() for item in raw_authority if str(item).strip()
        )
        return authority or None
