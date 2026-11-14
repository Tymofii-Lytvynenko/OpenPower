"""Read-only client view of an authoritative snapshot and its presentation data."""

from __future__ import annotations

import copy
from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import Any

import polars as pl

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


class _ReadOnlyJournalView:
    """Freeze journal records once, so repeated rendering does not recopy history."""

    __slots__ = ("domain_events", "command_results")

    def __init__(self, journal: Any, previous: _ReadOnlyJournalView | None = None) -> None:
        def freeze_suffix(records, old):
            # The decoder guarantees that a delta only appends journal records.
            if old is None or len(records) < len(old):
                return _read_only_value(records)
            return old + tuple(_read_only_value(record) for record in records[len(old):])

        object.__setattr__(self, "domain_events", freeze_suffix(
            journal.domain_events, None if previous is None else previous.domain_events
        ))
        object.__setattr__(self, "command_results", freeze_suffix(
            journal.command_results, None if previous is None else previous.command_results
        ))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"Snapshot journal attribute '{name}' is read-only.")


class _ReadOnlyTableMapping(Mapping[str, pl.DataFrame]):
    """Keep a stable table snapshot and return detached Polars handles on reads."""

    __slots__ = ("_tables",)

    def __init__(self, tables: Mapping[str, pl.DataFrame]) -> None:
        snapshot = {name: frame.clone() for name, frame in tables.items()}
        object.__setattr__(self, "_tables", MappingProxyType(snapshot))

    def __getitem__(self, name: str) -> pl.DataFrame:
        return self._tables[name].clone()

    def __iter__(self) -> Iterator[str]:
        return iter(self._tables)

    def __len__(self) -> int:
        return len(self._tables)

    def __contains__(self, name: object) -> bool:
        return name in self._tables

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Client table snapshots are read-only.")


def _read_only_value(value: Any) -> Any:
    if isinstance(value, pl.DataFrame):
        return value.clone()
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
    __slots__ = ("_state", "client_presentation", "presentation_state", "_tables", "_globals", "_events", "_current_actions", "_journal")

    def __init__(
        self,
        state: GameState,
        client_presentation: Mapping[str, object],
        presentation_state: ClientPresentationState,
        *,
        _previous_journal: _ReadOnlyJournalView | None = None,
    ) -> None:
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "client_presentation", MappingProxyType(dict(client_presentation)))
        object.__setattr__(self, "presentation_state", presentation_state)
        object.__setattr__(self, "_tables", _ReadOnlyTableMapping(state.tables))
        object.__setattr__(self, "_globals", _read_only_value(state.globals))
        object.__setattr__(self, "_journal", _ReadOnlyJournalView(state.journal, _previous_journal))
        object.__setattr__(self, "_events", copy.deepcopy(state.events))
        object.__setattr__(self, "_current_actions", copy.deepcopy(state.current_actions))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"Client snapshot attribute '{name}' is read-only.")

    @property
    def tables(self) -> Mapping[str, pl.DataFrame]:
        return self._tables

    @property
    def globals(self) -> Mapping[str, Any]:
        return self._globals

    @property
    def journal(self) -> _ReadOnlyJournalView:
        return self._journal

    @property
    def events(self) -> tuple[Any, ...]:
        return tuple(copy.deepcopy(self._events))

    @property
    def current_actions(self) -> tuple[Any, ...]:
        return tuple(copy.deepcopy(self._current_actions))

    @property
    def table_revisions(self) -> Mapping[str, int]:
        return MappingProxyType(dict(self._state.table_revisions))

    def get_table(self, name: str) -> Any:
        if name not in self._tables:
            raise KeyError(f"Table '{name}' not found in GameState.")
        return self._tables[name]

    def __getattr__(self, name: str) -> Any:
        if name in self._BLOCKED_MUTATORS:
            raise AttributeError(f"Client snapshots do not expose '{name}'.")
        if name.startswith("_"):
            raise AttributeError(name)
        return _read_only_value(getattr(self._state, name))
