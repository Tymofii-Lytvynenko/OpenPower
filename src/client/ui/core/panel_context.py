from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol, TYPE_CHECKING

from src.client.ui.components.shared.dirty_close_confirmation import SaveConfirmationPreferences

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
    presentation_total_minutes: Optional[float] = None
    on_deployment_drag_start: Optional[Callable[[str | list[str]], None]] = None
    save_confirmation_preferences: Optional[SaveConfirmationPreferences] = None
    on_notice: Optional[Callable[..., None]] = None
    on_question: Optional[Callable[..., bool]] = None
    player_country_tag: Optional[str] = None
    on_advisor_recommendation: Optional[Callable[[dict[str, Any]], None]] = None


class PanelRenderable(Protocol):
    def render(self, state: Any, context: PanelRenderContext) -> bool: ...
