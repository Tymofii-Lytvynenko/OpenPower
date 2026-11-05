"""Small action windows composed into the covert operations panel."""

from __future__ import annotations

from contextlib import contextmanager

from modules.base.systems.military.covert_operations_system import CovertOperationsSystem
from modules.base.systems.military.covert_policy import SKILL_LEVELS
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.layouts.gml_popup import gml_popup_modal
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_data import resolve_country_name
from src.shared.actions import (
    ActionCreateCovertCell,
    ActionStartCovertMission,
    ActionTrainCovertCell,
)
from src.shared.covert_mission_options import (
    MISSION_CATEGORY_OPTIONS,
    TARGET_SECTOR_OPTIONS,
    UNIT_CATEGORY_OPTIONS,
    allowed_complexities,
    country_resource_ids,
    default_complexity,
    mission_profile_type,
    resource_label,
)


class CovertActionWindows:
    """Own the transient form state for covert actions without owning game state."""

    _WINDOWS = {
        "create": ("Covert_Actions_Cell_Creation", "Create Covert Cell", "covert.cell_creation.dialog"),
        "train": ("Covert_Actions_Cell_Training", "Train Covert Cell", "covert.cell_training.dialog"),
        "mission": ("Covert_Actions_New_Mission", "New Covert Mission", "covert.new_mission.dialog"),
    }

    def __init__(self) -> None:
        self._active_window = ""
        self._popup_requested = False
        self._cell_name = "New covert cell"
        self._create_target = ""
        self._create_training_level = "Recruit"
        self._create_quote_key = None
        self._create_quote = None
        self._covert_operations = CovertOperationsSystem()
        self._training_cell = ""
        self._training_cell_ids: tuple[str, ...] = ()
        self._training_points = 100.0
        self._mission_cell = ""
        self._mission_cell_ids: tuple[str, ...] = ()
        self._mission_category = MISSION_CATEGORY_OPTIONS[0][0]
        self._mission_sector = "military"
        self._mission_complexity = "medium"
        self._mission_target = "ground"
        self._mission_cover_country = ""

    def open(self, window_id: str, cell_id: str = "", *, cell_ids: tuple[str, ...] = ()) -> None:
        self._active_window = window_id
        self._popup_requested = False
        selected_ids = tuple(dict.fromkeys(
            str(value) for value in (cell_ids or ((cell_id,) if cell_id else ())) if str(value)
        ))
        if window_id == "train":
            self._training_cell_ids = selected_ids
            self._training_cell = selected_ids[0] if selected_ids else ""
        elif window_id == "mission":
            self._mission_cell_ids = selected_ids
            self._mission_cell = selected_ids[0] if selected_ids else ""
        if window_id == "create":
            self._cell_name = ""
            self._create_training_level = "Recruit"
            self._create_quote_key = None
            self._create_quote = None
        if window_id == "mission":
            self._mission_category = MISSION_CATEGORY_OPTIONS[0][0]
            self._mission_sector = "military"
            self._mission_complexity = "medium"
            self._mission_target = "ground"
            self._mission_cover_country = ""

    def render(self, state, context: PanelRenderContext, presenter: MilitaryPresenter) -> None:
        if not context.is_own_country:
            if self._active_window and imgui.get_current_context() is not None:
                # State-only callers can reconcile country scope outside an active UI frame.
                imgui.close_current_popup()
            self._active_window = ""
            self._popup_requested = False
            return
        if self._active_window == "create":
            self._render_create(state, context)
        elif self._active_window == "train":
            self._render_train(state, context, presenter)
        elif self._active_window == "mission":
            self._render_mission(state, context, presenter)

    @contextmanager
    def _modal_window(self, window_id: str):
        template, title, test_id = self._WINDOWS[window_id]
        popup_id = f"CovertAction##{test_id}"
        if not self._popup_requested:
            imgui.open_popup(popup_id)
            self._popup_requested = True

        with gml_popup_modal(
            popup_id,
            template,
            title=title,
            test_id=test_id,
        ) as opened:
            if not opened:
                self._active_window = ""
                self._popup_requested = False
                yield False
                return

            yield True
            if self._active_window != window_id:
                imgui.close_current_popup()

    def _render_create(self, state, context: PanelRenderContext) -> None:
        with self._modal_window("create") as is_open:
            if not is_open:
                self._active_window = ""
                return

            with _compact_gml_controls():
                imgui.text_disabled(
                    "Cell name",
                    gml_id="Covert_Actions_Cell_Creation/frmInner/frmCell/lblCellName",
                )
                _, self._cell_name = imgui.input_text(
                    "##cell_name", self._cell_name, 96,
                    test_id="covert.cell_creation.name",
                    gml_id="Covert_Actions_Cell_Creation/frmInner/frmCell/edtName",
                )
                owner_tag = str(context.target_tag or "").upper()
                countries = self._country_tags(state, owner_tag)
                if not countries:
                    self._create_target = ""
                    imgui.text_disabled(
                        "No target countries are available in the current state.",
                        gml_id="Covert_Actions_Cell_Creation/frmInner/frmCell/lblCountry",
                    )
                else:
                    if self._create_target not in countries:
                        self._create_target = countries[0]
                    labels = [f"{tag} — {resolve_country_name(state, tag)}" for tag in countries]
                    selected_index = countries.index(self._create_target)
                    imgui.text_disabled(
                        "Target country",
                        gml_id="Covert_Actions_Cell_Creation/frmInner/frmCell/lblCountry",
                    )
                    _, selected_index = imgui.combo(
                        "##create_target", selected_index, labels,
                        test_id="covert.cell_creation.target",
                        gml_id="Covert_Actions_Cell_Creation/frmInner/frmCell/cboCountry",
                    )
                    self._create_target = countries[selected_index]

                if self._create_training_level not in SKILL_LEVELS:
                    self._create_training_level = SKILL_LEVELS[0]
                imgui.text_disabled(
                    "Training level",
                    gml_id="Covert_Actions_Cell_Creation/frmInner/frmCell/lblTraining",
                )
                _, training_index = imgui.combo(
                    "##create_training_level",
                    SKILL_LEVELS.index(self._create_training_level),
                    list(SKILL_LEVELS),
                    test_id="covert.cell_creation.training_level",
                    gml_id="Covert_Actions_Cell_Creation/frmInner/frmCell/cboTraining",
                )
                self._create_training_level = SKILL_LEVELS[training_index]

                quote_key = (owner_tag, self._create_target, self._create_training_level)
                if quote_key != self._create_quote_key:
                    self._create_quote = self._covert_operations.quote_cell_creation(
                        state, owner_tag, self._create_target, self._create_training_level
                    )
                    self._create_quote_key = quote_key
                quote = self._create_quote
                for label, gml_id in (
                    ("Setup cost", "lblSetupCost"),
                    ("Upkeep / day", "lblUpkeep"),
                    ("Deployment time", "lblTime"),
                ):
                    imgui.text_disabled(
                        label,
                        gml_id=f"Covert_Actions_Cell_Creation/frmInner/frmCell/{gml_id}",
                    )
                imgui.text(
                    f"${quote.setup_cost:,.0f}" if quote else "Unavailable",
                    test_id="covert.cell_creation.setup_cost",
                    gml_id="Covert_Actions_Cell_Creation/frmInner/frmCell/txtCost",
                )
                imgui.text(
                    f"${quote.daily_upkeep:,.2f}" if quote else "Unavailable",
                    test_id="covert.cell_creation.upkeep",
                    gml_id="Covert_Actions_Cell_Creation/frmInner/frmCell/txtUpkeep",
                )
                imgui.text(
                    self._format_deployment_time(quote.deployment_minutes, quote.rejection_reason)
                    if quote else "Unavailable",
                    test_id="covert.cell_creation.deployment_time",
                    gml_id="Covert_Actions_Cell_Creation/frmInner/frmCell/txtTime",
                )

                client = context.net_client
                can_create = bool(
                    context.is_own_country and client is not None
                    and self._cell_name.strip() and self._create_target
                )
                imgui.begin_disabled(not can_create)
                if imgui.button(
                    "Create cell",
                    test_id="covert.cell_creation.submit",
                    gml_id="Covert_Actions_Cell_Creation/frmInner/btnConfirm",
                ):
                    client.send_action(ActionCreateCovertCell(
                        player_id=client.player_id,
                        country_tag=owner_tag,
                        target_country_tag=self._create_target,
                        cell_name=self._cell_name.strip(),
                        training_level=self._create_training_level,
                    ))
                    self._cell_name = "New covert cell"
                    self._active_window = ""
                imgui.end_disabled()
                if imgui.button(
                    "Cancel",
                    test_id="covert.cell_creation.cancel",
                    gml_id="Covert_Actions_Cell_Creation/frmInner/btnCancel",
                ):
                    self._active_window = ""

    @staticmethod
    def _format_deployment_time(minutes: int | None, rejection_reason: str = "") -> str:
        if minutes is None:
            return "No legal route" if rejection_reason else "Unavailable"
        if minutes <= 0:
            return "Immediate"
        days, remainder = divmod(int(minutes), 1440)
        hours, extra_minutes = divmod(remainder, 60)
        if days:
            return f"{days} d {hours} h"
        if hours:
            return f"{hours} h {extra_minutes} m"
        return f"{extra_minutes} min"

    def _render_train(self, state, context: PanelRenderContext, presenter: MilitaryPresenter) -> None:
        with self._modal_window("train") as is_open:
            if not is_open:
                self._active_window = ""
                return

            cells = [
                row for row in presenter.covert_cells_for_country(
                    state, str(context.target_tag or "").upper()
                )
                if str(row.get("status") or "").lower() in {"active", "idle"}
            ]
            choices = [str(row.get("id") or "") for row in cells]
            if not choices:
                imgui.text_disabled("No active covert cell is available for training.")
                return

            selected_ids = self._training_cell_ids or ((self._training_cell,) if self._training_cell else ())
            selected_cells = [row for row in cells if str(row.get("id") or "") in selected_ids]
            selection_valid = bool(selected_ids) and len(selected_cells) == len(selected_ids)
            imgui.text_disabled(
                "Cell" if len(selected_ids) <= 1 else f"{len(selected_ids)} cells selected",
                gml_id="Covert_Actions_Cell_Training/frmInner/frmCell/lblCellName",
            )
            if len(selected_ids) <= 1 and selection_valid:
                labels = [str(row.get("cell_name") or row.get("id")) for row in cells]
                imgui.push_style_var(imgui.StyleVar_.frame_padding, (4.0, 0.0))
                _, selected_index = imgui.combo(
                    "##training_cell", choices.index(selected_ids[0]), labels,
                    test_id="covert.cell_training.cell",
                    gml_id="Covert_Actions_Cell_Training/frmInner/frmCell/txtName",
                )
                imgui.pop_style_var()
                selected_ids = (choices[selected_index],)
                self._training_cell_ids = selected_ids
                self._training_cell = selected_ids[0]
            elif len(selected_ids) <= 1:
                imgui.text_disabled(
                    "The selected cell is no longer available.",
                    test_id="covert.cell_training.stale_selection",
                )
            if len(selected_ids) > 1 and not selection_valid:
                imgui.text_disabled(
                    "One or more selected cells are no longer available.",
                    test_id="covert.cell_training.stale_selection",
                )
            imgui.text_disabled(
                "Training points",
                gml_id="Covert_Actions_Cell_Training/frmInner/frmCell/lblTraining",
            )
            imgui.push_style_var(imgui.StyleVar_.frame_padding, (4.0, 0.0))
            _, self._training_points = imgui.slider_float(
                "##training_points", self._training_points, 1.0, 100.0, "%.0f",
                test_id="covert.cell_training.points",
                gml_id="Covert_Actions_Cell_Training/frmInner/frmCell/txtTraining",
            )
            imgui.pop_style_var()

            client = context.net_client
            can_train = bool(context.is_own_country and client is not None and selection_valid)
            imgui.begin_disabled(not can_train)
            if imgui.button(
                "Train",
                test_id="covert.cell_training.submit",
                gml_id="Covert_Actions_Cell_Training/frmInner/btnConfirm",
            ):
                for cell_id in selected_ids:
                    client.send_action(ActionTrainCovertCell(
                        player_id=client.player_id,
                        cell_id=cell_id,
                        training_points=float(self._training_points),
                    ))
                self._active_window = ""
            imgui.end_disabled()
            if imgui.button(
                "Cancel",
                test_id="covert.cell_training.cancel",
                gml_id="Covert_Actions_Cell_Training/frmInner/btnCancel",
            ):
                self._active_window = ""

    def _render_mission(self, state, context: PanelRenderContext, presenter: MilitaryPresenter) -> None:
        with self._modal_window("mission") as is_open:
            if not is_open:
                self._active_window = ""
                return

            cells = [
                row for row in presenter.covert_cells_for_country(
                    state, str(context.target_tag or "").upper()
                )
                if str(row.get("status") or "").lower() in {"active", "idle"}
            ]
            choices = [str(row.get("id") or "") for row in cells]
            if not choices:
                imgui.text_disabled("No active covert cell is available for a mission.")
                return

            selected_ids = self._mission_cell_ids or ((self._mission_cell,) if self._mission_cell else ())
            if not selected_ids:
                selected_ids = (choices[0],)
                self._mission_cell_ids = selected_ids
                self._mission_cell = selected_ids[0]
            selected_cells = [row for row in cells if str(row.get("id") or "") in selected_ids]
            selection_valid = len(selected_cells) == len(selected_ids)
            target_tags = [str(row.get("target_country_id") or "").upper() for row in selected_cells]
            target_tag = target_tags[0] if len(selected_cells) == 1 else ""
            multiple_cells = len(selected_ids) > 1
            own_country = str(context.target_tag or "").upper()

            category_options = [
                (key, label) for key, label in MISSION_CATEGORY_OPTIONS
                if not (key == "coup_attempt" and own_country in target_tags)
            ]
            category_keys = [key for key, _label in category_options]
            category_labels = [label for _key, label in category_options]
            if self._mission_category not in category_keys:
                self._mission_category = category_keys[0]
            previous_category = self._mission_category
            imgui.text_disabled(
                "Mission type",
                gml_id="Covert_Actions_New_Mission/frmInner/frmMission/lblMissionType",
            )
            _, category_index = imgui.combo(
                "##mission_type", category_keys.index(self._mission_category), category_labels,
                test_id="covert.new_mission.type",
                gml_id="Covert_Actions_New_Mission/frmInner/frmMission/cboMissionType",
            )
            self._mission_category = category_keys[category_index]

            uses_sector = self._mission_category in {"espionage", "sabotage"}
            sector_keys = [key for key, _label in TARGET_SECTOR_OPTIONS]
            sector_labels = [label for _key, label in TARGET_SECTOR_OPTIONS]
            if not uses_sector:
                # REFERENCE clears the sector when a mission type does not target one.
                self._mission_sector = ""
            elif self._mission_sector not in sector_keys:
                self._mission_sector = "civilian" if previous_category != self._mission_category else "military"
            visible_sector_keys = sector_keys if uses_sector else [""]
            visible_sector_labels = sector_labels if uses_sector else [""]
            imgui.text_disabled(
                "Target sector",
                gml_id="Covert_Actions_New_Mission/frmInner/frmMission/lblTargetSector",
            )
            _, sector_index = imgui.combo(
                "##mission_sector", visible_sector_keys.index(self._mission_sector), visible_sector_labels,
                test_id="covert.new_mission.sector",
                gml_id="Covert_Actions_New_Mission/frmInner/frmMission/cboSector",
                gml_enabled=uses_sector,
            )
            if uses_sector:
                self._mission_sector = sector_keys[sector_index]

            target_sector = self._mission_sector if uses_sector else ""
            profile_type = mission_profile_type(self._mission_category, target_sector)
            complexity_options = allowed_complexities(profile_type, target_sector)
            if self._mission_complexity not in complexity_options:
                self._mission_complexity = default_complexity(profile_type)
            complexity_labels = [value.title() for value in complexity_options]
            imgui.text_disabled(
                "Complexity",
                gml_id="Covert_Actions_New_Mission/frmInner/frmMission/lblComplexity",
            )
            _, complexity_index = imgui.combo(
                "##mission_complexity", complexity_options.index(self._mission_complexity), complexity_labels,
                test_id="covert.new_mission.complexity",
                gml_id="Covert_Actions_New_Mission/frmInner/frmMission/cboComplexity",
            )
            self._mission_complexity = complexity_options[complexity_index]

            if target_sector == "civilian":
                if target_tags:
                    common_resources = set(country_resource_ids(state, target_tags[0]))
                    for tag in target_tags[1:]:
                        common_resources.intersection_update(country_resource_ids(state, tag))
                    target_options = sorted(common_resources)
                else:
                    target_options = []
                target_labels = [resource_label(value) for value in target_options]
            elif target_sector == "military":
                target_options = [key for key, _label in UNIT_CATEGORY_OPTIONS]
                target_labels = [label for _key, label in UNIT_CATEGORY_OPTIONS]
            else:
                target_options = []
                target_labels = []
            if not target_options:
                target_options = [""]
                target_labels = ["Unavailable" if uses_sector else ""]
            if self._mission_target not in target_options:
                self._mission_target = target_options[0]
            imgui.text_disabled(
                "Resource / unit",
                gml_id="Covert_Actions_New_Mission/frmInner/frmMission/lblResourceUnit",
            )
            _, target_index = imgui.combo(
                "##mission_target", target_options.index(self._mission_target), target_labels,
                test_id="covert.new_mission.target",
                gml_id="Covert_Actions_New_Mission/frmInner/frmMission/cboResourceUnit",
                gml_enabled=uses_sector and bool(target_options[0]),
            )
            self._mission_target = target_options[target_index]

            imgui.text_disabled(
                "Target country",
                gml_id="Covert_Actions_New_Mission/frmInner/frmMission/lblTargetCountry",
            )
            if not selection_valid or not target_tags:
                target_label = "Unavailable"
            elif multiple_cells:
                target_label = "—"
            else:
                target_label = f"{target_tag} — {resolve_country_name(state, target_tag)}"
            imgui.text(
                target_label,
                test_id="covert.new_mission.target_country",
                gml_id="Covert_Actions_New_Mission/frmInner/frmMission/txtCountry",
            )

            cover_choices = [""] + [
                tag for tag in self._country_tags(state, own_country, include_own=True)
                if tag != target_tag
            ] if not multiple_cells and target_tag else [""]
            if self._mission_cover_country not in cover_choices:
                self._mission_cover_country = ""
            cover_labels = [
                "No cover" if not tag else f"{tag} — {resolve_country_name(state, tag)}"
                for tag in cover_choices
            ]
            imgui.text_disabled(
                "Framed country",
                gml_id="Covert_Actions_New_Mission/frmInner/frmMission/lblFramedCountry",
            )
            imgui.begin_disabled(multiple_cells or not target_tag)
            _, cover_index = imgui.combo(
                "##mission_cover_country", cover_choices.index(self._mission_cover_country),
                cover_labels,
                test_id="covert.new_mission.cover_country",
                gml_id="Covert_Actions_New_Mission/frmInner/frmMission/cboCountry",
            )
            self._mission_cover_country = cover_choices[cover_index]
            imgui.end_disabled()

            client = context.net_client
            target_ready = not uses_sector or (
                bool(self._mission_target)
                and all(self._mission_target in country_resource_ids(state, tag)
                        for tag in target_tags)
                if target_sector == "civilian" else
                bool(self._mission_target)
            )
            can_start = bool(
                context.is_own_country and client is not None and selection_valid
                and selected_cells and all(target_tags) and target_ready
            )
            imgui.begin_disabled(not can_start)
            if imgui.button(
                "Prepare",
                test_id="covert.new_mission.submit",
                gml_id="Covert_Actions_New_Mission/frmInner/btnConfirm",
            ):
                for cell in selected_cells:
                    cell_target = str(cell.get("target_country_id") or "").upper()
                    client.send_action(ActionStartCovertMission(
                        player_id=client.player_id,
                        cell_id=str(cell.get("id") or ""),
                        mission_type=profile_type,
                        target_country_tag=cell_target,
                        cover_country_tag=(self._mission_cover_country or None)
                        if not multiple_cells else None,
                        requires_execution_confirmation=True,
                        target_sector=target_sector or None,
                        complexity=self._mission_complexity,
                        target_resource_id=(self._mission_target if target_sector == "civilian" else None),
                        target_unit_category=(self._mission_target if target_sector == "military" else None),
                    ))
                self._active_window = ""
            imgui.end_disabled()
            if imgui.button(
                "Cancel",
                test_id="covert.new_mission.cancel",
                gml_id="Covert_Actions_New_Mission/frmInner/btnCancel",
            ):
                self._active_window = ""

    @staticmethod
    def _country_tags(state, own_country_tag: str, include_own: bool = False) -> list[str]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return []
        return sorted(
            str(country_id).strip().upper()
            for country_id in countries["id"].to_list()
            if str(country_id or "").strip()
            and (include_own or str(country_id).strip().upper() != own_country_tag)
        )


@contextmanager
def _compact_gml_controls():
    """Match standard ImGui controls to the short heights used by the source dialogs."""
    imgui.push_style_var(imgui.StyleVar_.frame_padding, (4.0, 0.0))
    try:
        yield
    finally:
        imgui.pop_style_var()
