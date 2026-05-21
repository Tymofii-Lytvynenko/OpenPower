from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List

from src.client.ui.core.panel_context import PanelRenderable, PanelRenderContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PanelSpec:
    id: str
    factory: Callable[[], PanelRenderable]
    icon: str = ""
    color: tuple = (1, 1, 1, 1)
    default_visible: bool = False
    show_in_toggle_bar: bool = True


@dataclass
class PanelEntry:
    id: str
    instance: PanelRenderable
    visible: bool
    icon: str = ""
    color: tuple = (1, 1, 1, 1)
    show_in_toggle_bar: bool = True


class PanelManager:
    """Owns panel instances, visibility, and safe frame rendering."""

    def __init__(self):
        self._panels: Dict[str, PanelEntry] = {}

    def register(
        self,
        pid: str,
        panel: PanelRenderable,
        icon: str = "",
        color: tuple | None = None,
        visible: bool = False,
        show_in_toggle_bar: bool = True,
    ) -> None:
        self._panels[pid] = PanelEntry(
            id=pid,
            instance=panel,
            visible=visible,
            icon=icon,
            color=color or (1, 1, 1, 1),
            show_in_toggle_bar=show_in_toggle_bar,
        )

    def register_spec(self, spec: PanelSpec) -> None:
        self.register(
            spec.id,
            spec.factory(),
            icon=spec.icon,
            color=spec.color,
            visible=spec.default_visible,
            show_in_toggle_bar=spec.show_in_toggle_bar,
        )

    def toggle(self, pid: str) -> None:
        entry = self._panels.get(pid)
        if entry is not None:
            entry.visible = not entry.visible

    def set_visible(self, pid: str, is_visible: bool) -> None:
        entry = self._panels.get(pid)
        if entry is not None:
            entry.visible = is_visible

    def is_visible(self, pid: str) -> bool:
        entry = self._panels.get(pid)
        return bool(entry and entry.visible)

    def render_all(self, state, context: PanelRenderContext) -> None:
        """Render all visible panels without letting one broken panel kill the frame."""
        for entry in self._panels.values():
            if not entry.visible:
                continue

            try:
                keep_open = entry.instance.render(state, context)
            except Exception:
                logger.exception("Panel '%s' failed during render", entry.id)
                continue

            if keep_open is False:
                entry.visible = False

    def get_entries(self, toggle_bar_only: bool = False) -> List[PanelEntry]:
        entries = list(self._panels.values())
        if toggle_bar_only:
            return [entry for entry in entries if entry.show_in_toggle_bar]
        return entries
