from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.shared.config import GameConfig
from src.shared.protocols import SessionPort


@runtime_checkable
class ClientSessionPort(SessionPort, Protocol):
    """Runtime services required by client-owned session startup flows."""

    map_data: Any
    progress_queue: Any

    def tick(self, delta_time: float) -> None:
        ...

    def shutdown(self) -> None:
        ...


@runtime_checkable
class SessionFactory(Protocol):
    """Creates a client proxy without exposing server implementation details."""

    def __call__(
        self,
        config: GameConfig,
        *,
        save_name: str | None = None,
        player_tag: str | None = None,
    ) -> ClientSessionPort:
        ...
