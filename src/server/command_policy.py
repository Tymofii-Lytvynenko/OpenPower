from __future__ import annotations

import dataclasses
import math
from typing import Any

from src.shared.commands import CommandEnvelope
from src.shared.state import GameState


def validate_finite_payload(command: CommandEnvelope, state: GameState) -> str | None:
    """Rejects non-finite numeric payloads before they reach Polars expressions."""

    def invalid(value: Any) -> bool:
        if isinstance(value, float):
            return not math.isfinite(value)
        if dataclasses.is_dataclass(value):
            return any(invalid(getattr(value, field.name)) for field in dataclasses.fields(value))
        if isinstance(value, dict):
            return any(invalid(item) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(invalid(item) for item in value)
        return False

    if invalid(command.action):
        return "Command payload contains a non-finite number."
    return None


def authorize_country_scope(command: CommandEnvelope, state: GameState) -> str | None:
    """Applies optional actor-to-country permissions configured by the host."""

    permissions = state.globals.get("command_permissions")
    if not isinstance(permissions, dict):
        return None
    raw_allowed = permissions.get(command.actor_id)
    if raw_allowed == "*":
        return None
    if not isinstance(raw_allowed, (list, tuple, set)):
        return f"Actor '{command.actor_id}' has no country permissions."

    allowed = {str(country_tag) for country_tag in raw_allowed}
    scoped_tags = {
        str(getattr(command.action, field.name))
        for field in dataclasses.fields(command.action)
        if field.name.endswith("country_tag")
        and getattr(command.action, field.name, None)
    }
    denied = sorted(scoped_tags - allowed)
    if denied:
        return f"Actor '{command.actor_id}' cannot control countries {denied}."
    return None
