from __future__ import annotations

from collections.abc import Callable

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.theme import GAMETHEME


class PartySelectionWindow:
    """Source-sized party picker backed by OpenPower political-party rows."""

    def __init__(self, on_confirm: Callable[[str], None]) -> None:
        self._on_confirm = on_confirm
        self._open = False
        self._country_id = ""
        self._parties: list[dict] = []
        self._selected_party_id = ""

    @property
    def is_open(self) -> bool:
        return self._open

    @staticmethod
    def party_options(state, country_id: str) -> list[dict]:
        parties = state.tables.get("political_parties")
        if parties is None or not {"country_id", "party_id"}.issubset(parties.columns):
            return []

        country = str(country_id or "").strip().upper()
        rows = [
            row
            for row in parties.to_dicts()
            if str(row.get("country_id") or "").strip().upper() == country
            and str(row.get("party_id") or "").strip()
        ]
        return sorted(
            rows,
            key=lambda row: (
                -_finite_number(row.get("support_share")),
                str(row.get("party_id") or "").casefold(),
            ),
        )

    @classmethod
    def default_party_id(cls, state, country_id: str) -> str:
        options = cls.party_options(state, country_id)
        if not options:
            return ""

        governments = state.tables.get("country_governments")
        ruling_party = ""
        if governments is not None and {"country_id", "ruling_party_id"}.issubset(governments.columns):
            ruling_party = next(
                (
                    str(row.get("ruling_party_id") or "").strip()
                    for row in governments.to_dicts()
                    if str(row.get("country_id") or "").strip().upper()
                    == str(country_id or "").strip().upper()
                ),
                "",
            )
        return next(
            (
                str(row.get("party_id") or "").strip()
                for row in options
                if str(row.get("party_id") or "").strip().casefold() == ruling_party.casefold()
            ),
            str(options[0].get("party_id") or "").strip(),
        )

    def show(self, state, country_id: str, selected_party_id: str = "") -> None:
        self._country_id = str(country_id or "").strip().upper()
        self._parties = self.party_options(state, self._country_id)
        valid_ids = {str(row.get("party_id") or "").strip() for row in self._parties}
        selected = str(selected_party_id or "").strip()
        self._selected_party_id = (
            selected if selected in valid_ids else self.default_party_id(state, self._country_id)
        )
        self._open = True

    def render(self, screen_width: float, screen_height: float) -> None:
        if not self._open:
            return

        is_open = True
        imgui.push_style_color(imgui.Col_.window_bg, GAMETHEME.colors.bg_popup)
        try:
            with WindowManager.window(
                "SELECT POLITICAL PARTY",
                x=(float(screen_width) - 339.0) / 2.0,
                y=(float(screen_height) - 197.0) / 2.0,
                w=339,
                h=197,
                test_id="new_game.party_selection.dialog",
                gml_template="Party_Selection_Window",
                follow_position=True,
                closable=True,
            ) as is_open:
                if is_open:
                    self._render_content()
        finally:
            imgui.pop_style_color()
        if not is_open:
            self._open = False

    def _render_content(self) -> None:
        ui = GMLWidgets("Party_Selection_Window")
        list_open = imgui.begin_child(
            "PartyChoices",
            (290.0, 121.0),
            False,
            test_id="new_game.party_selection.list",
            gml_id=ui.path("frmInner/frmParties/lstParties"),
        )
        if list_open:
            for row in self._parties:
                party_id = str(row.get("party_id") or "").strip()
                name = str(row.get("display_name") or party_id)
                support = _finite_number(row.get("support_share")) * 100.0
                if imgui.selectable(
                    f"{name}##party-{party_id}",
                    self._selected_party_id == party_id,
                    test_id=f"new_game.party_selection.party.{party_id}",
                    gml_id=ui.path("frmInner/frmParties/lstParties"),
                )[0]:
                    self._selected_party_id = party_id
                imgui.same_line(218.0)
                imgui.text(f"{support:.1f} %")
            if not self._parties:
                imgui.text_disabled("No political-party data available.")
        imgui.end_child()

        if ui.button(
            "frmInner/btnConfirm",
            "CONFIRM",
            "new_game.party_selection.confirm",
            enabled=bool(self._selected_party_id),
            dynamic_enabled=True,
        ):
            self._on_confirm(self._selected_party_id)
            self._open = False
        if ui.button("frmInner/btnCancel", "CANCEL", "new_game.party_selection.cancel"):
            self._open = False


def _finite_number(value) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return result if result == result and abs(result) != float("inf") else 0.0
