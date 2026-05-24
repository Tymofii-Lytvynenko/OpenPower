from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from imgui_bundle import imgui

from src.client.ui.core.composer import UIComposer


class UnitContextMenu:
    """Right-click popup for map units."""

    def __init__(
        self,
        composer: UIComposer,
        on_deselect: Callable[[], None],
        on_view_units_list: Callable[[str], None],
    ):
        self.composer = composer
        self._on_deselect = on_deselect
        self._on_view_units_list = on_view_units_list
        self._unit_id: Optional[str] = None
        self._queued_open = False
        self._popup_id = "unit_context_menu"

    def show(self, unit_id: str) -> None:
        self._unit_id = unit_id
        self._queued_open = True

    def render(self) -> None:
        if self._queued_open:
            imgui.open_popup(self._popup_id)
            self._queued_open = False

        if self.composer.begin_popup(self._popup_id):
            self._render_content()
            self.composer.end_popup()

    def _render_content(self) -> None:
        if not self._unit_id:
            return

        imgui.text_disabled(self._unit_id)
        imgui.separator()

        self.composer.draw_menu_item("Move", "0")
        self.composer.draw_menu_item("Move and attack", "0")

        if self.composer.begin_menu("Change status"):
            self.composer.draw_menu_item("Park")
            self.composer.draw_menu_item("Ready")
            self.composer.draw_menu_item("Fortify")
            self.composer.end_menu()

        if self.composer.draw_menu_item("Deselect"):
            self._on_deselect()

        self.composer.draw_menu_item("Merge with")
        self.composer.draw_menu_item("Split")

        if self.composer.draw_menu_item("View units list"):
            self._on_view_units_list(self._unit_id)
