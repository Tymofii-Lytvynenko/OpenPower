"""Read-only client view of an authoritative snapshot and its presentation data."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from src.shared.geo_names import DEFAULT_GEO_LANGUAGE_CODE
from src.shared.state import GameState


class _ReadOnlyObjectView:
    """Expose data attributes without granting writes to nested snapshot objects."""

    __slots__ = ("_source",)

    def __init__(self, source: object) -> None:
        object.__setattr__(self, "_source", source)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        value = getattr(self._source, name)
        if callable(value):
            raise AttributeError(f"Snapshot data method '{name}' is not exposed to the client.")
        return _read_only_value(value)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"Snapshot data attribute '{name}' is read-only.")


def _read_only_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _read_only_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_read_only_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_read_only_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(_read_only_value(item) for item in value)
    if hasattr(value, "__dict__"):
        return _ReadOnlyObjectView(value)
    return value


class ClientPresentationState:
    """Settings owned by the UI and kept outside the simulation snapshot."""

    def __init__(self, geo_language_code: str = DEFAULT_GEO_LANGUAGE_CODE) -> None:
        self.geo_language_code = geo_language_code


class ClientGameStateView:
    """Expose snapshot data for rendering without exposing GameState mutators."""

    _BLOCKED_MUTATORS = frozenset(
        {
            "bind_schema_registry",
            "create_checkpoint",
            "remove_table",
            "restore_checkpoint",
            "schema_registry",
            "to_ipc",
            "update_table",
        }
    )
    __slots__ = ("_state", "client_presentation", "presentation_state", "_tables", "_globals")

    def __init__(
        self,
        state: GameState,
        client_presentation: Mapping[str, object],
        presentation_state: ClientPresentationState,
    ) -> None:
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "client_presentation", MappingProxyType(dict(client_presentation)))
        object.__setattr__(self, "presentation_state", presentation_state)
        object.__setattr__(self, "_tables", MappingProxyType(dict(state.tables)))
        object.__setattr__(self, "_globals", _read_only_value(state.globals))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"Client snapshot attribute '{name}' is read-only.")

    @property
    def tables(self) -> Mapping[str, Any]:
        return self._tables

    @property
    def globals(self) -> Mapping[str, Any]:
        return self._globals

    @property
    def events(self) -> tuple[Any, ...]:
        return tuple(self._state.events)

    @property
    def current_actions(self) -> tuple[Any, ...]:
        return tuple(self._state.current_actions)

    @property
    def table_revisions(self) -> Mapping[str, int]:
        return MappingProxyType(dict(self._state.table_revisions))

    def get_table(self, name: str) -> Any:
        return self._state.get_table(name)

    def __getattr__(self, name: str) -> Any:
        if name in self._BLOCKED_MUTATORS:
            raise AttributeError(f"Client snapshots do not expose '{name}'.")
        if name.startswith("_"):
            raise AttributeError(name)
        return _read_only_value(getattr(self._state, name))
