"""Authoritative per-country advisor mode settings."""

from __future__ import annotations

from typing import Any

import polars as pl

from modules.base.systems.world.authority_policy import player_controls_country
from src.shared.actions import ActionUpdateAdvisorSettings
from src.shared.advisor_settings import ADVISOR_MODES, ADVISOR_STATUS_COLUMNS
from src.shared.determinism import DeterministicRuntime
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


class AdvisorSettingsSystem(ISystem):
    """Stores validated advisor modes on each authoritative country row."""

    access = SystemAccess(
        reads=frozenset({"countries"}),
        writes=frozenset({"countries"}),
        handles=frozenset({ActionUpdateAdvisorSettings}),
        phase=SystemPhase.POST_PROCESS,
    )

    @property
    def id(self) -> str:
        return "base.advisor_settings"

    @property
    def dependencies(self) -> list[str]:
        return ["base.bootstrap"]

    def update(self, state: GameState, delta_time: float) -> None:
        actions = [
            action for action in state.current_actions
            if isinstance(action, ActionUpdateAdvisorSettings)
        ]
        if not actions:
            return

        countries = state.tables.get("countries")
        if countries is None or "id" not in countries.columns:
            for action in actions:
                self._record_result(
                    state, action, "rejected", "Country data is unavailable.", ""
                )
            return

        rows = countries.to_dicts()
        country_indexes: dict[str, list[int]] = {}
        for index, row in enumerate(rows):
            tag = self._tag(row.get("id"))
            if tag:
                country_indexes.setdefault(tag, []).append(index)

        changed = False
        for action in actions:
            country = self._tag(action.country_tag)
            modes = {
                domain: str(getattr(action, f"{domain}_status", "") or "").strip().lower()
                for domain in ADVISOR_STATUS_COLUMNS
            }
            reason = self._validate(state, action, country, modes, country_indexes)
            if reason:
                self._record_result(state, action, "rejected", reason, country)
                continue

            row = rows[country_indexes[country][0]]
            for domain, column in ADVISOR_STATUS_COLUMNS.items():
                row[column] = modes[domain]
            changed = True
            self._record_result(
                state,
                action,
                "applied",
                "Advisor settings updated.",
                country,
            )

        if changed:
            state.update_table(
                "countries",
                pl.DataFrame(rows, schema=countries.schema, strict=False),
            )

    @classmethod
    def _validate(
        cls,
        state: GameState,
        action: ActionUpdateAdvisorSettings,
        country: str,
        modes: dict[str, str],
        country_indexes: dict[str, list[int]],
    ) -> str:
        if country not in country_indexes:
            return "The selected country is unavailable."
        if len(country_indexes[country]) != 1:
            return "The selected country is ambiguous."
        if not player_controls_country(state, action.player_id, country):
            return "The issuer does not control this country's advisor settings."
        if any(mode not in ADVISOR_MODES for mode in modes.values()):
            return "Choose a valid advisor mode for economy, politics, and military."
        return ""

    @staticmethod
    def _record_result(
        state: GameState,
        action: ActionUpdateAdvisorSettings,
        status: str,
        reason: str,
        country: str,
    ) -> None:
        result_id = DeterministicRuntime(state.determinism).next_id(
            "advisor-settings-command", int(state.globals.get("tick", 0))
        )
        state.journal.append_command_result(
            {
                "result_id": result_id,
                "action_type": type(action).__name__,
                "player_id": str(action.player_id),
                "status": status,
                "reason": reason,
                "game_minute": int(state.time.total_minutes),
                "country_id": country,
            }
        )

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()
