from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from src.client.services.network_client_service import NetworkClient


@dataclass(frozen=True, slots=True)
class PanelRenderContext:
    """Frame-local context shared by HUD panels.

    Keeping panel context in one typed object avoids fragile **kwargs coupling and
    makes new panel dependencies explicit.
    """

    target_tag: str
    is_own_country: bool
    selected_region_id: Optional[int] = None
    on_focus_request: Optional[Callable[[int], None]] = None
    net_client: Optional["NetworkClient"] = None


class PanelRenderable(Protocol):
    def render(self, state: Any, context: PanelRenderContext) -> bool: ...
