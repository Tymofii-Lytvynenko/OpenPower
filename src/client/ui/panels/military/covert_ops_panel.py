"""Compose covert cell actions and selected mission in the source GML frames."""
from __future__ import annotations

import math

import polars as pl

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.components.shared.generic_message_dialog import GenericMessageDialog
from src.client.ui.layouts.gml_layout import gml_child_frame
from src.client.ui.layouts.gml_rows import gml_row
from src.client.ui.panels.military.covert_action_windows import CovertActionWindows
from src.client.ui.panels.military.covert_intelligence_window import CovertIntelligenceWindow
from src.client.ui.panels.military.covert_roster_controls import CovertRosterControls
from src.client.ui.panels.military.covert_selection import CovertSelection, mission_index
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.shared.actions import ActionExecuteCovertMission, ActionCancelCovertMission, ActionRetireCovertCell
from src.shared.covert_mission_options import UNIT_CATEGORY_OPTIONS, resource_label
from src.client.ui.panels.shared.panel_data import resolve_country_name
from modules.base.systems.military.covert_policy import domestic_security_coverage


class CovertOpsPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()
        self._action_windows = CovertActionWindows()
        self._selection = CovertSelection()
        self._intelligence = CovertIntelligenceWindow()
        self._scroll_cell = ""
        self._notice = GenericMessageDialog()
        self._roster_controls = CovertRosterControls()

    def request_cell(self, cell_id, mission_id=""):
        self._selection.request(cell_id, mission_id)

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("COVERT OPS", x=260, y=100, test_id="covert_ops.panel",
                                  padding=(0, 0)) as opened:
            if not opened:
                return False
            self._render_content(state, context)
        self._action_windows.render(state, context, self._presenter)
        self._intelligence.render(state, context, self._presenter)
        self._notice.render()
        return True

    def _render_content(self, state, context):
        country = str(context.target_tag or "").upper()
        self._roster_controls.update(state, context)
        # Cell locations, skill and readiness are private roster data. Detected
        # foreign operations remain available in the separately redacted findings.
        cells = self._presenter.covert_cells_for_country(state, country) if context.is_own_country else []
        cells = [row for row in cells if str(row.get("country_id") or "").upper() == country
                 and row.get("status") != "retired"]
        missions = [row for row in self._presenter.covert_missions_for_country(state, country)
                    if row.get("owner_country_id") == country] if context.is_own_country else []
        previous_cell = self._selection.cell_id
        cell, warning = self._selection.reconcile(country, cells, missions)
        if cell and previous_cell != self._selection.cell_id:
            self._scroll_cell = self._selection.cell_id
        if warning:
            (context.on_notice or self._notice.enqueue)("Covert operations", warning, severity="warning")
        ui = GMLWidgets("Covert_Actions_Window/frmInner")
        for slot, label in (("lblTitle", "COVERT CELLS"), ("lblName", "NAME"),
                            ("lblCountry", "ASSIGNED COUNTRY"), ("lblStatus", "STATUS"),
                            ("lblUpkeep", "UPKEEP / DAY")):
            ui.text("frmCell/" + slot, label)
        # This exported heading is a transparent-text type inside a meter slot,
        # so the normal text widget mapper falls back to the window origin.
        ui.text_at("frmCell/lblProgress", "PROGRESS", test_id="covert_ops.progress.heading")
        by_cell = mission_index(missions)
        with gml_child_frame(ui.path("frmCell/lstCell"), bordered=False):
            if not cells:
                imgui.text_wrapped("No covert cells are registered." if context.is_own_country else
                                   "Covert cell details are available only for your country.",
                                   test_id="covert_ops.cells.empty")
            for row in cells:
                key = str(row.get("id"))
                with gml_row("lstCovertActionsItem", key) as row_ui:
                    row_ui.text("txtName", row.get("cell_name") or key,
                        color=GAMETHEME.colors.info if key in self._selection.selected_cell_ids else None,
                        test_id=f"covert_ops.cell.{key}.select",
                        tooltip=f"{row.get('cell_name') or key} · {row.get('skill_level') or 'Unknown'}")
                    if imgui.is_item_clicked():
                        io = imgui.get_io()
                        self._selection.select_extended(
                            key,
                            [str(item.get("id")) for item in cells],
                            ctrl=bool(io.key_ctrl),
                            shift=bool(io.key_shift),
                        )
                    row_ui.text("picGrade", str(row.get("skill_level") or "?")[:1],
                                tooltip=str(row.get("skill_level") or "Unknown skill"))
                    self._roster_controls.render(row_ui, row, by_cell.get(key), state, context, self._selection.select)
                    mission = by_cell.get(key)
                    fraction = self._progress(row, mission)
                    row_ui.meter("frmProgress", fraction, GAMETHEME.colors.info)
                    row_ui.text("frmProgress", f"{fraction * 100:.0f}%", test_id=f"covert_ops.cell.{key}.progress")
                    row_ui.text("txtUpkeep", f"$ {float(row.get('upkeep') or 0):,.2f}", right=True)
                    if key == self._scroll_cell:
                        imgui.set_scroll_here_y(0.5)
                        self._scroll_cell = ""
        selected_ids = set(self._selection.selected_cell_ids)
        selected_cells = [row for row in cells if str(row.get("id")) in selected_ids]
        cell = next((row for row in cells if str(row.get("id")) == self._selection.cell_id), None)
        mission = by_cell.get(self._selection.cell_id)
        self._render_actions(ui, selected_cells, by_cell, context)
        self._render_mission(ui, state, cell, mission, len(selected_cells))
        ui.text("frmUpkeep/lblProtection", "PROTECTION")
        protection = self._protection_coverage(state, country, cells) if context.is_own_country else None
        protection_text = f"{protection * 100.0:.1f}%" if protection is not None else "Unknown"
        protection_tooltip = (
            "OpenPower estimate from active domestic-security cells and country population. "
            "It uses the same coverage rule as covert mission detection and differs from REFERENCE's NationalSecurity formula."
            if protection is not None else
            "Unknown because authoritative regional population is unavailable."
        )
        ui.text("frmUpkeep/txtProtection", protection_text,
                test_id="covert_ops.protection", tooltip=protection_tooltip)
        ui.text("frmUpkeep/lblUpkeep", "ROSTER / DAY",
                tooltip="Sum of configured daily upkeep. Actual charges depend on cell state.")
        ui.text("frmUpkeep/txtUpkeep", f"$ {sum(float(r.get('upkeep') or 0) for r in cells if r.get('status') not in {'retired', 'captured', 'lost'}):,.2f}" if context.is_own_country else "Unknown", right=True)
        if ui.button_at("frmUpkeep", "Intelligence", "covert_ops.open_intelligence", offset=(-322, 5), size=(123, 18)):
            self._intelligence.is_open = True

    @staticmethod
    def _protection_coverage(state, country: str, cells: list[dict]) -> float | None:
        """Reuse the detection coverage rule so the overview reports simulation-backed protection."""

        regions = state.tables.get("regions")
        if regions is None or "owner" not in regions.columns:
            return None
        population_column = next(
            (name for name in ("population", "total_population") if name in regions.columns),
            None,
        )
        if population_column is None:
            return None

        country_tag = str(country or "").strip().upper()
        population_rows = regions.filter(
            pl.col("owner").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase()
            == country_tag
        )
        if population_rows.is_empty():
            return None
        population = float(
            population_rows.get_column(population_column)
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
            .sum()
        )
        if not math.isfinite(population) or population <= 0.0:
            return None

        security_cell_count = sum(
            1 for cell in cells
            if str(cell.get("assignment") or "").strip().lower() == "domestic_security"
            and str(cell.get("status") or "").strip().lower() == "active"
            and str(cell.get("location_country_id") or "").strip().upper() == country_tag
        )
        return domestic_security_coverage(security_cell_count, population, state.globals)

    @staticmethod
    def _progress(cell, mission):
        if mission and mission.get("status") in {"preparation", "ready"}:
            value = mission.get("preparation_progress")
        elif cell.get("status") == "training":
            required = float(cell.get("training_required") or 0)
            value = float(cell.get("training_progress") or 0) / required if required > 0 else 0
        else:
            value = cell.get("readiness")
        try:
            return min(1., max(0., float(value))) if math.isfinite(float(value)) else 0.
        except (TypeError, ValueError, OverflowError):
            return 0.

    def _render_actions(self, ui, selected_cells, missions_by_cell, context):
        can_command = context.is_own_country and context.net_client is not None
        if ui.button("frmCell/btnNewCell", "Create cell", "covert_ops.open_cell_creation", enabled=can_command):
            self._action_windows.open("create")

        selected_ids = tuple(str(row.get("id") or "") for row in selected_cells)
        selected_missions = [missions_by_cell.get(cell_id) for cell_id in selected_ids]
        has_pending = any(cell_id in self._roster_controls.pending for cell_id in selected_ids)
        training_ready = bool(selected_cells) and all(
            row.get("status") in {"active", "idle"}
            and str(row.get("skill_level") or "") != "Elite"
            for row in selected_cells
        )
        mission_ready = bool(selected_cells) and all(
            row.get("status") in {"active", "idle"}
            and not (mission and mission.get("status") in {"preparation", "ready", "executing", "cleanup"})
            for row, mission in zip(selected_cells, selected_missions)
        )
        execution_ready = bool(selected_cells) and all(
            row.get("status") == "ready" and mission and mission.get("status") == "ready"
            for row, mission in zip(selected_cells, selected_missions)
        )
        cancellation_ready = bool(selected_cells) and all(
            mission and mission.get("status") in {"preparation", "ready"}
            for mission in selected_missions
        )
        retirement_ready = bool(selected_cells) and all(
            row.get("status") not in {"captured", "lost", "retired"}
            for row in selected_cells
        )

        if ui.button("frmCell/btnTrainCell", "Train", "covert_ops.open_cell_training",
                     enabled=can_command and training_ready and not has_pending):
            self._action_windows.open("train", cell_ids=selected_ids)
        if ui.button("frmCell/btnDisbandCell", "Disband", "covert_ops.retire",
                     enabled=can_command and retirement_ready and not has_pending):
            for cell_id in selected_ids:
                context.net_client.send_action(
                    ActionRetireCovertCell(context.net_client.player_id, cell_id)
                )

        mission_label = "Execute mission" if execution_ready else "New mission"
        mission_action = "covert_ops.execute" if execution_ready else "covert_ops.open_new_mission"
        if ui.button("frmCell/btnNewMission", mission_label, mission_action,
                     enabled=can_command and not has_pending and (mission_ready or execution_ready)):
            if execution_ready:
                for mission in selected_missions:
                    context.net_client.send_action(
                        ActionExecuteCovertMission(context.net_client.player_id, str(mission["id"]))
                    )
            else:
                self._action_windows.open("mission", cell_ids=selected_ids)
        if ui.button("frmCell/btnCancelMission", "Cancel mission", "covert_ops.cancel_mission",
                     enabled=can_command and not has_pending and cancellation_ready):
            for mission in selected_missions:
                context.net_client.send_action(
                    ActionCancelCovertMission(context.net_client.player_id, str(mission["id"]))
                )

    def _render_mission(self, ui, state, cell, mission, selection_count):
        if selection_count > 1:
            name = f"{selection_count} CELLS SELECTED"
        else:
            name = str((cell or {}).get("cell_name") or self._selection.cell_id or "No selected cell")
        ui.text("frmMission/lblTitle", "MISSION · " + name, test_id="covert_ops.selected_cell")
        for key, label in (("lblType", "TYPE"), ("lblSector", "SECTOR"), ("lblComplexity", "COMPLEXITY"),
                           ("lblResourceUnit", "RESOURCE / UNIT"), ("lblFramedCountry", "FRAMED COUNTRY")):
            ui.text("frmMission/" + key, label)
        kind = str((mission or {}).get("mission_type") or "")
        stored_sector = str((mission or {}).get("target_sector") or "").lower()
        sector = stored_sector.title() if stored_sector else (
            "Civilian" if kind.startswith("civilian_") else
            "Military" if kind.startswith("military_") else
            "Political" if kind else "—"
        )
        target = "—"
        if mission and sector == "Civilian":
            target = resource_label(mission.get("target_resource_id")) if mission.get("target_resource_id") else "Not recorded"
        elif mission and sector == "Military":
            unit_labels = dict(UNIT_CATEGORY_OPTIONS)
            target = unit_labels.get(str(mission.get("target_unit_category") or ""), "Not recorded")
        framed_tag = str((mission or {}).get("framed_country_id") or "")
        # Missions store a country tag, so resolve it against the same snapshot as the panel.
        framed_country = resolve_country_name(state, framed_tag) if framed_tag else "None"
        for key, value in (("txtMission", kind.replace("_", " ").title() or "—"),
                           ("txtSector", sector),
                           ("txtComplexity", str(mission.get("complexity") or "Not recorded").title() if mission else "—"),
                           ("txtResourceUnit", target),
                           ("txtFramedCountry", framed_country if mission else "—")):
            ui.text("frmMission/" + key, value, test_id="covert_ops.mission." + key)
