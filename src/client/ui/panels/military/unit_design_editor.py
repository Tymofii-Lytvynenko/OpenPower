"""OpenPower's role-based creation flow in the source-sized design builder."""

from __future__ import annotations

from dataclasses import dataclass

from modules.base.systems.military.capability_catalog import DEFAULT_ROLE_PROFILES
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import active_gml_layout
from src.client.ui.panels.military.unit_design_widgets import render_capability_rows
from src.client.ui.panels.military.unit_type_options import unit_type_options_for_roles
from src.shared.actions import ActionCreateUnitDesign


@dataclass(frozen=True, slots=True)
class _PendingDesignSubmission:
    country_tag: str
    display_name: str
    known_design_ids: frozenset[str]


class UnitDesignEditor:
    def __init__(self) -> None:
        self._is_open = False
        self._role = "infantry"
        self._name = ""
        self._cost = 0.0
        self._maintenance_cost = 0.0
        self._locked = False
        self._capabilities_by_role: dict[str, dict[str, float]] = {}
        self._pending_submission: _PendingDesignSubmission | None = None

    def open(self, role: str | None = None) -> None:
        if role in DEFAULT_ROLE_PROFILES:
            self._role = role
        self._name = ""
        self._cost = 0.0
        self._maintenance_cost = 0.0
        self._pending_submission = None
        self._capabilities_by_role = {
            self._role: dict(DEFAULT_ROLE_PROFILES[self._role].capabilities),
        }
        self._is_open = True

    def render(self, state, context: PanelRenderContext) -> None:
        if not self._is_open:
            return
        self._reset_after_authoritative_create(state)
        if not self._is_open:
            return

        flags = imgui.WindowFlags_.no_move if self._locked else 0
        with WindowManager.window(
            "CREATE UNIT DESIGN", x=307, y=51, w=666, h=618,
            test_id="unit_design.create.dialog",
            gml_template="Unit_New_Design",
            flags=flags,
        ) as is_open:
            if not is_open:
                self._is_open = False
                return

            ui = GMLWidgets("Unit_New_Design")
            self._draw_source_frames(ui)
            _, self._locked = ui.toggle(
                "frmTitle/togLockWindow", self._locked,
                "unit_design.create.lock", icon="L",
                color=GAMETHEME.colors.accent,
                tooltip="Lock the design window position.",
            )

            role_options = unit_type_options_for_roles(DEFAULT_ROLE_PROFILES)
            role_names = [option.role for option in role_options]
            if self._role not in role_names:
                self._role = role_names[0]
            previous_role = self._role
            imgui.text_disabled(
                "UNIT TYPE",
                gml_id=ui.path("frmDesignSpecs/frmUnitInfo/lblUnitType"),
            )
            _, role_index = imgui.combo(
                "##unit_design.create.role", role_names.index(self._role),
                [option.label for option in role_options],
                test_id="unit_design.create.role",
                gml_id=ui.path("frmDesignSpecs/frmUnitInfo/cboUnitType"),
            )
            self._role = role_names[role_index]
            profile = DEFAULT_ROLE_PROFILES[self._role]
            if self._role != previous_role:
                self._capabilities_by_role.setdefault(
                    self._role, dict(profile.capabilities),
                )
            capabilities = self._capabilities_by_role.setdefault(
                self._role, dict(profile.capabilities),
            )

            imgui.text_disabled(
                "DESIGN NAME",
                gml_id=ui.path("frmDesignSpecs/frmUnitInfo/lblUnitName"),
            )
            _, self._name = imgui.input_text(
                "##unit_design.create.name", self._name, 96,
                test_id="unit_design.create.name",
                gml_id=ui.path("frmDesignSpecs/frmUnitInfo/edtName"),
            )
            imgui.text_wrapped(
                f"{profile.domain.title()} role. Target rules are fixed; capability values use OpenPower ranges.",
                gml_id=ui.path("frmDesignSpecs/frmUnitInfo/frmDescription/txtText"),
            )

            imgui.text_disabled(
                "UNIT COST",
                gml_id=ui.path(
                    "frmDesignSpecs/frm1stLvlInner1/frmUnitInfo1/lblUnitCost",
                ),
            )
            _, self._cost = imgui.input_float(
                "##unit_design.create.cost", self._cost, 0.0, 0.0, "%.2f",
                test_id="unit_design.create.cost",
                gml_id=ui.path(
                    "frmDesignSpecs/frm1stLvlInner1/frmUnitInfo1/txtCost",
                ),
            )
            imgui.text_disabled(
                "ADJUSTABLE CAPABILITIES",
                gml_id=ui.path("frmDesignSpecs/frm1stLvlInner1/lblTitle"),
            )
            render_capability_rows(
                ui,
                "frmDesignSpecs/frm1stLvlInner1/frmInner",
                capabilities,
                editable=True,
                test_id_prefix="unit_design.create.capability",
            )

            self._render_model_placeholder(ui, profile.domain)
            self._render_unavailable_model_controls(ui)
            self._render_maintenance_field(ui)

            client = context.net_client
            can_submit = bool(
                context.is_own_country and client is not None
                and self._name.strip() and self._cost > 0.0
                and self._maintenance_cost >= 0.0
            )
            # The source's 84-pixel confirmation slot clips the longer English caption.
            if ui.button(
                "frmAction/btnConfirm", "CREATE", "unit_design.create.submit",
                enabled=can_submit,
                tooltip="Create this design." if can_submit
                else "Enter a name and positive cost in your own country.",
            ):
                submitted_name = self._name.strip()
                designs = state.tables.get("unit_designs")
                known_design_ids = frozenset(
                    str(row.get("id") or "")
                    for row in ([] if designs is None else designs.to_dicts())
                )
                design_stats = {
                    key: float(value) for key, value in capabilities.items()
                }
                design_stats.update({
                    "cost": float(self._cost),
                    "maintenance_cost": float(self._maintenance_cost),
                })
                client.send_action(ActionCreateUnitDesign(
                    player_id=client.player_id,
                    country_tag=str(context.target_tag or "").upper(),
                    branch=profile.domain,
                    class_name=self._role,
                    display_name=submitted_name,
                    stats=design_stats,
                ))
                self._pending_submission = _PendingDesignSubmission(
                    str(context.target_tag or "").upper(),
                    submitted_name,
                    known_design_ids,
                )

            if ui.button(
                "frmAction/btnCancel", "CANCEL", "unit_design.create.cancel",
                tooltip="Close the design builder.",
            ):
                self._is_open = False

    def _reset_after_authoritative_create(self, state) -> None:
        pending = self._pending_submission
        if pending is None:
            return

        designs = state.tables.get("unit_designs")
        if designs is None or designs.is_empty():
            return

        accepted = any(
            str(row.get("id") or "") not in pending.known_design_ids
            and str(row.get("country_id") or "").strip().upper() == pending.country_tag
            and str(row.get("display_name") or "").strip() == pending.display_name
            for row in designs.to_dicts()
        )
        if not accepted:
            return

        # Keep submitted values until the authoritative design row exists so a rejected save remains editable.
        self._pending_submission = None
        self._name = ""
        self._cost = 0.0
        self._maintenance_cost = 0.0
        self._capabilities_by_role[self._role] = dict(
            DEFAULT_ROLE_PROFILES[self._role].capabilities,
        )
        self._is_open = False

    @staticmethod
    def _draw_source_frames(ui: GMLWidgets) -> None:
        for slot in (
            "frmDesignSpecs",
            "frmDesignSpecs/frmUnitInfo",
            "frmDesignSpecs/frm1stLvlInner1",
            "frmDesignSpecs/frm1stLvlInner1/frmInner",
            "frmDesignSpecs/frm1stLvlInner1/frmUnitInfo1",
            "frmDesignView",
            "frmBuild",
            "frmBuild/frmPage",
            "frmBuild/frmParts",
            "frmBuild/frmTextures",
            "frmAction",
        ):
            ui.frame(slot)

    @staticmethod
    def _render_model_placeholder(ui: GMLWidgets, domain: str) -> None:
        session = active_gml_layout()
        rect = ui.rect("frmDesignView/Model")
        if session is None or rect is None:
            return

        x = session.window_position[0] + rect.x + 8.0 - imgui.get_scroll_x()
        y = session.window_position[1] + rect.y + rect.height / 2.0 - imgui.get_scroll_y()
        imgui.set_cursor_screen_pos((x, y))
        imgui.text_disabled(f"{domain.title()} role profile")
        imgui.set_cursor_screen_pos((x, y + 20.0))
        imgui.text_disabled("3D model assets are unavailable")

    @staticmethod
    def _render_unavailable_model_controls(ui: GMLWidgets) -> None:
        imgui.begin_disabled()
        try:
            imgui.combo(
                "##unit_design.create.piece_type", 0, ["Unavailable"],
                test_id="unit_design.create.piece_type",
                gml_id=ui.path("frmBuild/frmPage/cboType"),
            )
        finally:
            imgui.end_disabled()
        if imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
            imgui.set_tooltip("Model part data and assets are unavailable in OpenPower.")

        ui.button(
            "frmBuild/frmPage/btnLeft", "<", "unit_design.create.page.left",
            enabled=False, tooltip="Model pages are unavailable in OpenPower.",
        )
        ui.button(
            "frmBuild/frmPage/btnRight", ">", "unit_design.create.page.right",
            enabled=False, tooltip="Model pages are unavailable in OpenPower.",
        )
        for slot, label in (
            ("frmBuild/frmParts/btnLeft", "LEFT"),
            ("frmBuild/frmParts/btnMiddle", "CENTER"),
            ("frmBuild/frmParts/btnRight", "RIGHT"),
        ):
            ui.button(
                slot, label, f"unit_design.create.part.{label.lower()}",
                enabled=False, tooltip="Visual part selection is unavailable in OpenPower.",
            )
        for index in range(1, 9):
            ui.button(
                f"frmBuild/frmTextures/btn{index}", str(index),
                f"unit_design.create.texture.{index}",
                enabled=False, tooltip="Visual texture assets are unavailable in OpenPower.",
            )

    def _render_maintenance_field(self, ui: GMLWidgets) -> None:
        session = active_gml_layout()
        rect = ui.rect("frmAction")
        if session is None or rect is None:
            return

        origin_x = session.window_position[0] + rect.x + 12.0 - imgui.get_scroll_x()
        origin_y = session.window_position[1] + rect.y + 14.0 - imgui.get_scroll_y()
        imgui.set_cursor_screen_pos((origin_x, origin_y))
        imgui.text_disabled("ANNUAL UPKEEP / STRENGTH")
        imgui.set_cursor_screen_pos((origin_x + 190.0, origin_y - 1.0))
        imgui.set_next_item_width(190.0)
        _, self._maintenance_cost = imgui.input_float(
            "##unit_design.create.maintenance", self._maintenance_cost,
            0.0, 0.0, "%.2f",
            test_id="unit_design.create.maintenance",
        )
