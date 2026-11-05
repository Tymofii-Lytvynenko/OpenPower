"""Read-only combat result preserving the source summary geometry."""
from __future__ import annotations

from src.client.renderers.flag_renderer import FlagRenderer
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.window_placement import center_window
from src.client.ui.layouts.gml_layout import gml_child_frame
from src.client.ui.panels.shared.panel_data import normalize_side, resolve_country_name, resolve_region_name
from src.client.ui.panels.shared.unit_categories import unit_category


class BattleSummaryDialog:
    def __init__(self, test_prefix="battle.summary"):
        self._result: dict | None = None
        self._losses: list[dict] | None = None
        self._prefix = test_prefix
        self._flags = FlagRenderer()

    def dismiss(self):
        self._result = None
        self._losses = None

    def show(self, payload: dict, *, losses: list[dict] | None = None):
        self._result = dict(payload)
        self._losses = None if losses is None else [dict(row) for row in losses]

    def render(self, state):
        result = self._result
        if result is None:
            return
        viewport = imgui.get_io().display_size
        x, y = center_window((viewport.x, viewport.y), (283, 306))
        with WindowManager.window(
            f"Battle summary###{self._prefix}", x=x, y=y,
            w=283, h=306, test_id=f"{self._prefix}.dialog", gml_template="Battle_Summary_Window",
        ) as opened:
            if not opened:
                self.dismiss()
                return
            ui = GMLWidgets("Battle_Summary_Window/frmInner/frmInner")
            ui.text("frmBattleInfo/lblBattleName", "BATTLE RESULT")
            region = resolve_region_name(state, int(result.get("region_id") or 0))
            ui.text("frmBattleInfo/txtBattleName", region, test_id=f"{self._prefix}.region")
            battles = state.tables.get("battles")
            battle = next((row for row in battles.to_dicts()
                           if str(row.get("id")) == str(result.get("battle_id"))), {}) if battles is not None else {}

            # REFERENCE pane A is the defending side and pane B is the attacking side.
            panes = (
                ("A", "side_b_losses", "side_b_country_ids", "defender_side", "SIDE_B", "DEFENDERS"),
                ("B", "side_a_losses", "side_a_country_ids", "attacker_side", "SIDE_A", "ATTACKERS"),
            )
            for pane, loss_key, country_key, battle_country_key, combat_side, label in panes:
                frame = f"frmSide{pane}"
                countries = normalize_side(result.get(country_key))
                countries = countries or normalize_side(battle.get(battle_country_key))
                ui.text(f"{frame}/lblSide", label, test_id=f"{self._prefix}.side.{pane}")
                ui.text(
                    f"{frame}/lblLosses", "LOSSES",
                    tooltip=f"Total recorded personnel losses: {int(result.get(loss_key) or 0):,}",
                    test_id=f"{self._prefix}.losses.heading.{pane}",
                )
                self._render_countries(state, ui, frame, pane, countries)

                category_losses = _category_loss_counts(
                    self._losses, combat_side, int(result.get(loss_key) or 0),
                )
                for category in "IGAN":
                    ui.text(f"{frame}/lbl{category}", category)
                    value = "—" if category_losses is None else str(category_losses[category])
                    ui.text(
                        f"{frame}/txt{category}", value,
                        tooltip="OpenPower personnel casualties grouped by force category.",
                        test_id=f"{self._prefix}.category.{pane}.{category}",
                    )

                status = _outcome_for_side(result, combat_side, countries)
                ui.text(f"{frame}/lblStatus", status, test_id=f"{self._prefix}.outcome.{pane}")

    def _render_countries(self, state, ui, frame: str, pane: str, countries: tuple[str, ...]) -> None:
        with gml_child_frame(
            ui.path(f"{frame}/lstCountries"), padding=(0.0, 0.0), bordered=False,
            test_id=f"{self._prefix}.country_list.{pane}",
        ) as list_open:
            if not list_open:
                return
            if not countries:
                imgui.set_cursor_pos((2.0, 2.0))
                imgui.text("Not recorded", test_id=f"{self._prefix}.countries.{pane}.empty")
                return
            for index, tag in enumerate(countries):
                row_y = float(index * 16)
                imgui.set_cursor_pos((2.0, row_y + 2.0))
                self._flags.draw_flag(tag, 22.0, 13.0)
                imgui.set_cursor_pos((25.0, row_y + 1.0))
                imgui.text(tag[:3].upper(), test_id=f"{self._prefix}.countries.{pane}.{index}")
                if imgui.is_item_hovered():
                    imgui.set_tooltip(resolve_country_name(state, tag))


def _category_loss_counts(
    losses: list[dict] | None,
    combat_side: str,
    expected_total: int,
) -> dict[str, int] | None:
    if not losses:
        return None
    counts = dict.fromkeys("IGAN", 0)
    recorded_total = 0
    for row in losses:
        if _combat_side(row.get("side")) != combat_side:
            continue
        category = unit_category(row.get("unit_type"))
        if category is None:
            return None
        losses_for_row = max(0, int(row.get("losses") or 0))
        counts[category] += losses_for_row
        recorded_total += losses_for_row
    # A side total cannot safely fill source category slots when detail rows are incomplete.
    if recorded_total != max(0, int(expected_total)):
        return None
    return counts


def _combat_side(value: object) -> str:
    side = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if side in {"A", "SIDE_A", "ATTACKER", "ATTACKERS"}:
        return "SIDE_A"
    if side in {"B", "SIDE_B", "DEFENDER", "DEFENDERS"}:
        return "SIDE_B"
    return ""


def _outcome_for_side(result: dict, combat_side: str, countries: tuple[str, ...]) -> str:
    victor_side = _combat_side(result.get("victor_side"))
    if victor_side:
        return "Victory" if victor_side == combat_side else "Defeat"
    victor_tag = str(result.get("victor_tag") or "").strip().upper()
    if victor_tag in {"", "NONE", "NULL", "UNKNOWN", "UNDECIDED", "N/A"}:
        return "Unknown"
    return "Victory" if victor_tag in countries else "Defeat" if countries else "Unknown"
