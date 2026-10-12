"""Authoritative language and religion policy lifecycle."""

from __future__ import annotations

import math
from typing import Any

import polars as pl

from modules.base.systems.politics.identity_policy import (
    IDENTITY_TYPES,
    apply_identity_assimilation,
    calculate_identity_signals,
    normalize_identity_status,
)
from modules.base.systems.world.authority_policy import player_controls_country
from src.shared.actions import ActionSetCountryIdentityPolicy
from src.shared.determinism import DeterministicRuntime
from src.shared.events import (
    EventCountryIdentityCompositionChanged,
    EventCountryIdentityPolicyChanged,
    EventNewDay,
)
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


class IdentityPolicySystem(ISystem):
    """Applies identity-policy actions and exposes their bounded political effects."""

    access = SystemAccess(
        reads=frozenset(
            {
                "country_identity_groups",
                "country_identity_signals",
                "political_effects",
                "political_history",
            }
        ),
        writes=frozenset(
            {
                "country_identity_groups",
                "country_identity_signals",
                "political_effects",
                "political_history",
            }
        ),
        handles=frozenset({ActionSetCountryIdentityPolicy}),
        phase=SystemPhase.POLITICS,
    )

    @property
    def id(self) -> str:
        return "base.identity_policy"

    @property
    def dependencies(self) -> list[str]:
        return ["base.bootstrap"]

    def update(self, state: GameState, delta_time: float) -> None:
        has_identity_action = any(
            isinstance(action, ActionSetCountryIdentityPolicy)
            for action in state.current_actions
        )
        has_new_day = not state.time.is_paused and any(
            isinstance(event, EventNewDay) for event in state.events
        )
        if not has_identity_action and not has_new_day:
            return
        groups_frame = state.tables.get("country_identity_groups")
        if groups_frame is None or groups_frame.is_empty():
            return

        groups = groups_frame.to_dicts()
        changed_countries: set[str] = set()
        policies_changed = False
        now = max(0, int(state.time.total_minutes))

        for action in state.current_actions:
            if not isinstance(action, ActionSetCountryIdentityPolicy):
                continue
            changed_country = self._apply_policy(state, groups, action, now)
            if changed_country:
                changed_countries.add(changed_country)
                policies_changed = True

        composition_changes = []
        if has_new_day:
            composition_changes = apply_identity_assimilation(groups, now)
            changed_countries.update(
                str(change["country_id"]) for change in composition_changes
            )
            if composition_changes:
                policies_changed = True
                for change in composition_changes:
                    state.events.append(
                        EventCountryIdentityCompositionChanged(
                            country_id=str(change["country_id"]),
                            identity_type=str(change["identity_type"]),
                            source_identity_id=str(change["source_identity_id"]),
                            destination_identity_id=str(change["destination_identity_id"]),
                            share_points=float(change["share_points"]),
                            at_minute=now,
                        )
                    )

        signals_frame = state.tables.get("country_identity_signals")
        if signals_frame is None or signals_frame.is_empty():
            changed_countries.update(
                sorted({str(row.get("country_id") or "").upper() for row in groups})
            )
            policies_changed = True

        if not policies_changed:
            return

        state.update_table(
            "country_identity_groups",
            pl.DataFrame(groups, schema=groups_frame.schema, strict=False),
        )
        self._refresh_country_signals(state, groups, changed_countries, now)
        self._refresh_political_effects(state, groups, changed_countries, now)

    def _apply_policy(
        self,
        state: GameState,
        groups: list[dict[str, Any]],
        action: ActionSetCountryIdentityPolicy,
        now: int,
    ) -> str:
        country_id = self._tag(action.country_tag)
        identity_type = str(action.identity_type or "").strip().casefold()
        identity_id = str(action.identity_id or "").strip().casefold()
        status = normalize_identity_status(action.status)
        reason = ""

        if not player_controls_country(state, action.player_id, country_id):
            reason = "The issuer does not control this country's identity policy."
        elif identity_type not in IDENTITY_TYPES:
            reason = "Identity type must be language or religion."
        elif not identity_id or not status:
            reason = "Choose a listed identity group and a supported legal status."

        target = next(
            (
                row
                for row in groups
                if self._tag(row.get("country_id")) == country_id
                and str(row.get("identity_type") or "").strip().casefold() == identity_type
                and str(row.get("identity_id") or "").strip().casefold() == identity_id
            ),
            None,
        )
        if not reason and target is None:
            reason = "That identity group is not present in the country's data."
        if not reason and bool(target.get("is_other_bucket")):
            reason = "The aggregated Other category cannot receive a legal-status policy."
        if not reason and status in {"restricted", "illegal"}:
            alternatives = [
                row
                for row in groups
                if self._tag(row.get("country_id")) == country_id
                and str(row.get("identity_type") or "").strip().casefold() == identity_type
                and row is not target
                and normalize_identity_status(row.get("legal_status")) in {"official", "legal"}
                and self._share(row.get("population_share")) > 0.0
            ]
            if not alternatives:
                reason = "At least one other language or religion group must remain legally recognized."

        previous_status = "" if target is None else str(target.get("legal_status") or "legal")
        if not reason and previous_status == status:
            self._command_result(state, action, "applied", "Identity policy already has this status.")
            return ""

        result = "rejected" if reason else "accepted"
        if not reason and target is not None:
            target["legal_status"] = status
            target["last_policy_change_minute"] = now
            for row in groups:
                if (
                    self._tag(row.get("country_id")) == country_id
                    and str(row.get("identity_type") or "").strip().casefold() == identity_type
                ):
                    row["last_updated_minute"] = now
            state.events.append(
                EventCountryIdentityPolicyChanged(
                    country_id=country_id,
                    identity_type=identity_type,
                    identity_id=identity_id,
                    previous_status=previous_status,
                    new_status=status,
                    population_share=self._share(target.get("population_share")),
                    at_minute=now,
                    reason=f"{identity_type.title()} policy changed from {previous_status} to {status}.",
                )
            )

        self._record_history(
            state,
            country_id,
            identity_type,
            identity_id,
            previous_status,
            status,
            result,
            reason or f"{identity_type.title()} policy changed from {previous_status} to {status}.",
            now,
        )
        self._command_result(
            state,
            action,
            "rejected" if reason else "applied",
            reason or f"{identity_type.title()} policy changed from {previous_status} to {status}.",
        )
        return country_id if not reason else ""

    @staticmethod
    def _command_result(
        state: GameState,
        action: ActionSetCountryIdentityPolicy,
        status: str,
        reason: str,
    ) -> None:
        state.journal.append_command_result(
            {
                "tick": int(state.globals.get("tick", 0)),
                "player_id": str(action.player_id or ""),
                "action_type": type(action).__name__,
                "status": status,
                "reason": reason,
            }
        )

    def _refresh_country_signals(
        self,
        state: GameState,
        groups: list[dict[str, Any]],
        changed_countries: set[str],
        now: int,
    ) -> None:
        frame = state.tables.get("country_identity_signals")
        if frame is None:
            return
        rows = [] if frame.is_empty() else frame.to_dicts()
        by_country = {self._tag(row.get("country_id")): row for row in rows}
        groups_by_country: dict[str, list[dict[str, Any]]] = {}
        for row in groups:
            country_id = self._tag(row.get("country_id"))
            if country_id in changed_countries:
                groups_by_country.setdefault(country_id, []).append(row)

        for country_id in sorted(changed_countries):
            metrics = calculate_identity_signals(groups_by_country.get(country_id, []))
            by_country[country_id] = {
                "country_id": country_id,
                "language_group_count": int(metrics["language_group_count"]),
                "religion_group_count": int(metrics["religion_group_count"]),
                "official_share": float(metrics["official_share"]),
                "restricted_share": float(metrics["restricted_share"]),
                "illegal_share": float(metrics["illegal_share"]),
                "policy_pressure": float(metrics["policy_pressure"]),
                "updated_at_minute": now,
            }
        state.update_table(
            "country_identity_signals",
            pl.DataFrame(
                [by_country[key] for key in sorted(by_country)],
                schema=frame.schema,
                strict=False,
            ),
        )

    def _refresh_political_effects(
        self,
        state: GameState,
        groups: list[dict[str, Any]],
        changed_countries: set[str],
        now: int,
    ) -> None:
        frame = state.tables.get("political_effects")
        if frame is None or not changed_countries:
            return
        rows = [] if frame.is_empty() else frame.to_dicts()
        groups_by_country: dict[str, list[dict[str, Any]]] = {}
        for row in groups:
            country_id = self._tag(row.get("country_id"))
            if country_id in changed_countries:
                groups_by_country.setdefault(country_id, []).append(row)

        for country_id in sorted(changed_countries):
            rights_id = f"identity-policy-rights-{country_id}"
            stability_id = f"identity-policy-stability-{country_id}"
            metrics = calculate_identity_signals(groups_by_country.get(country_id, []))
            rows = [
                row for row in rows
                if str(row.get("id") or "") not in {rights_id, stability_id}
            ]
            effects = (
                {
                    "id": rights_id,
                    "domain": "rights",
                    "effect": "public_rights",
                    "value": float(metrics["rights_signal"]),
                    "reason": "Legal recognition and identity restrictions shape public-rights cohesion.",
                },
                {
                    "id": stability_id,
                    "domain": "stability",
                    "effect": "stability_modifier",
                    "value": -float(metrics["policy_pressure"]) * 0.08,
                    "reason": "Restricted or illegal identity groups add bounded political pressure.",
                },
            )
            for effect in effects:
                if abs(float(effect["value"])) < 1e-9:
                    continue
                rows.append(
                    {
                        **effect,
                        "country_id": country_id,
                        "source_type": "identity_policy",
                        "source_id": country_id,
                        "effective_at_minute": now,
                        "expires_at_minute": 0,
                        "status": "active",
                    }
                )
        state.update_table(
            "political_effects",
            pl.DataFrame(rows, schema=frame.schema, strict=False),
        )

    def _record_history(
        self,
        state: GameState,
        country_id: str,
        identity_type: str,
        identity_id: str,
        previous_status: str,
        new_status: str,
        result: str,
        reason: str,
        now: int,
    ) -> None:
        frame = state.tables.get("political_history")
        if frame is None:
            return
        rows = [] if frame.is_empty() else frame.to_dicts()
        identifier = DeterministicRuntime(state.determinism).next_id(
            "identity-policy", int(state.globals.get("tick", 0))
        )
        rows.append(
            {
                "id": identifier,
                "country_id": country_id,
                "event_type": "identity_policy",
                "source_type": "identity_policy",
                "source_id": f"{identity_type}:{identity_id}",
                "game_minute": now,
                "previous_value": previous_status,
                "new_value": new_status,
                "reason": reason,
                "result": result,
            }
        )
        state.update_table(
            "political_history",
            pl.DataFrame(rows, schema=frame.schema, strict=False),
        )

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _share(value: Any) -> float:
        try:
            share = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return min(100.0, max(0.0, share)) if math.isfinite(share) else 0.0
