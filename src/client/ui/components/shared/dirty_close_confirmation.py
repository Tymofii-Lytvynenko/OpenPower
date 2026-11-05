from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.testability import semantic_region
from src.client.ui.layouts.gml_popup import gml_popup_modal


class CloseDecision(Enum):
    APPLY = "apply"
    DISCARD = "discard"


@dataclass(slots=True)
class SaveConfirmationPreferences:
    do_not_show: bool = False
    always_apply: bool = False

    def remembered_decision(self) -> CloseDecision | None:
        if not self.do_not_show:
            return None
        return CloseDecision.APPLY if self.always_apply else CloseDecision.DISCARD

    def remember_decision(self, decision: CloseDecision, remember: bool) -> None:
        self.do_not_show = remember
        if remember:
            self.always_apply = decision is CloseDecision.APPLY


class DirtyCloseConfirmation:
    def __init__(self, test_id: str, message: str):
        self.test_id = test_id
        self.message = message
        self._pending = False
        self._popup_requested = False
        self._remember_choice = False

    @property
    def pending(self) -> bool:
        return self._pending

    def request_close(
        self,
        preferences: SaveConfirmationPreferences,
        *,
        can_apply: bool,
    ) -> CloseDecision | None:
        if self._pending:
            return None
        decision = preferences.remembered_decision()
        if decision is not None:
            if decision is CloseDecision.APPLY and not can_apply:
                return CloseDecision.DISCARD
            return decision
        self._pending = True
        return None

    def render(
        self,
        preferences: SaveConfirmationPreferences,
        *,
        can_apply: bool,
    ) -> CloseDecision | None:
        if not self._pending:
            return None

        popup_id = f"Save Confirmation##{self.test_id}"
        if not self._popup_requested:
            imgui.open_popup(popup_id)
            self._popup_requested = True

        decision = None
        with gml_popup_modal(popup_id, "Save_Confirmation_Window", movable=True) as opened:
            if not opened:
                return None
            with semantic_region(f"{self.test_id}.confirmation", "Save confirmation"):
                ui = GMLWidgets("Save_Confirmation_Window")
                # Flowing 150px buttons overflowed this 221x95 source dialog;
                # bind every control explicitly so closing remains actionable.
                ui.text("lblText1", "Apply changes before", tooltip=self.message)
                ui.text("lblText2", "closing?", tooltip=self.message)
                ui.text("picExclamation", "!")
                _, self._remember_choice = imgui.checkbox(
                    "##remember", self._remember_choice,
                    test_id=f"{self.test_id}.remember",
                    gml_id="Save_Confirmation_Window/togRemember",
                )
                ui.text("lblText3", "Remember this choice")
                apply_clicked = ui.button("btnApply", "Apply", f"{self.test_id}.apply", enabled=can_apply)
                discard_clicked = ui.button("btnDont", "Discard", f"{self.test_id}.discard")

                if apply_clicked and can_apply:
                    decision = CloseDecision.APPLY
                elif discard_clicked:
                    decision = CloseDecision.DISCARD

            if decision is not None:
                preferences.remember_decision(decision, self._remember_choice)
                imgui.close_current_popup()

        if decision is not None:
            self._pending = False
            self._popup_requested = False
        return decision
