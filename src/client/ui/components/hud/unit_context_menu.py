from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.composer import UIComposer


class UnitContextMenu:
    """Right-click popup for map units."""

    def __init__(
        self,
        composer: UIComposer,
        on_deselect: Callable[[], None],
        on_view_units_list: Callable[[str], None],
        on_set_readiness: Callable[[str, str], None] | None = None,
        on_split: Callable[[str],None] | None = None,
        on_merge: Callable[[str],None] | None = None,
        on_move_requested: Callable[[str], None] | None = None,
        on_attack_requested: Callable[[str], None] | None = None,
    ):
        self.composer = composer
        self._on_deselect = on_deselect
        self._on_view_units_list = on_view_units_list
        self._on_set_readiness = on_set_readiness
        self._on_split,self._on_merge = on_split,on_merge
        self._on_move_requested = on_move_requested
        self._on_attack_requested = on_attack_requested
        self._unit_id: Optional[str] = None
        self._orders_enabled = True
        self._queued_open = False
        self._popup_id = "unit_context_menu"

    def show(self, unit_id: str, orders_enabled: bool = True) -> None:
        self._unit_id = unit_id
        self._orders_enabled = orders_enabled
        self._queued_open = True

    def render(self) -> None:
        if self._queued_open:
            imgui.open_popup(self._popup_id)
            self._queued_open = False

        if imgui.begin_popup(self._popup_id, test_id="unit.context.popup"):
            self._render_content()
            imgui.end_popup()

    def _render_content(self) -> None:
        if not self._unit_id:
            return

        imgui.text_disabled(self._unit_id)
        imgui.separator()

        self._order_item(
            "Move",
            self._on_move_requested,
            "Click a destination on the map. Access restrictions and invasion confirmation still apply.",
        )
        self._order_item(
            "Move and attack",
            self._on_attack_requested,
            "Choose a destination. Hostile contact engages automatically; neutral entry still requires confirmation.",
        )

        if self.composer.begin_menu("Change status"):
            if self.composer.draw_menu_item("Park") and self._on_set_readiness:
                self._on_set_readiness(self._unit_id, "parked")
            if self.composer.draw_menu_item("Ready") and self._on_set_readiness:
                self._on_set_readiness(self._unit_id, "ready")
            if self.composer.draw_menu_item("Fortify") and self._on_set_readiness:
                self._on_set_readiness(self._unit_id, "fortified")
            self.composer.end_menu()

        if self.composer.draw_menu_item("Deselect"):
            self._on_deselect()

        self._reorganization_item("Merge with",self._on_merge)
        self._reorganization_item("Split",self._on_split)

        if imgui.menu_item("View units list","",False,True,test_id="unit.context.view_list")[0]:
            self._on_view_units_list(self._unit_id)

    @staticmethod
    def _unavailable_item(label: str, reason: str) -> None:
        # These placeholders previously looked actionable but had no callback.
        imgui.begin_disabled()
        imgui.menu_item(label, "", False, False, test_id=f"unit.context.{label.lower().replace(' ', '_')}")
        imgui.end_disabled()
        if imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
            imgui.set_tooltip(reason)

    def _order_item(self, label: str, callback, reason: str) -> None:
        if callback is None:
            self._unavailable_item(label, reason)
        elif not self._orders_enabled:
            self._unavailable_item(label, "Select one of your own units before issuing this order.")
        else:
            test_id = f"unit.context.{label.lower().replace(' ', '_')}"
            if imgui.menu_item(label, "", False, True, test_id=test_id)[0]:
                callback(self._unit_id)

    def _reorganization_item(self,label,callback):
        if callback is None:
            self._unavailable_item(label,"Select your own unit in a connected game.")
        elif imgui.menu_item(label,"",False,True,
                test_id=f"unit.context.{label.lower().replace(' ','_')}")[0]:
            callback(self._unit_id)
